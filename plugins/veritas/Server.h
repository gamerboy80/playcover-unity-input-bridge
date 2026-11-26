#import <Foundation/Foundation.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <poll.h>
#import "WebSocket.h"

static BOOL VeritasClientExpired(NSDictionary *client, NSTimeInterval now) {
    NSTimeInterval ping = [client[@"pingSent"] doubleValue];
    return now - [client[@"seen"] doubleValue] > 60 || (ping > 0 && now - ping > 20);
}
static inline NSString *VeritasJSON(id object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    return data ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : @"{}";
}

// Socket.IO / Engine.IO v4 on the same loopback port as upstream.
@interface VeritasServer : NSObject
@property(nonatomic, copy) NSString *status;
- (void)start;
- (void)publish:(NSString *)event data:(NSDictionary *)data;
@end
@implementation VeritasServer {
    int _listener;
    NSUInteger _connections;
    dispatch_source_t _source;
    NSMutableDictionary<NSString *, NSMutableDictionary *> *_clients;
}
- (instancetype)init {
    if ((self = [super init])) { _listener = -1; _clients = [NSMutableDictionary dictionary]; self.status = @"API stopped"; }
    return self;
}
- (void)publish:(NSString *)event data:(NSDictionary *)data {
    NSString *packet = [@"42" stringByAppendingString:VeritasJSON(@[event, data])];
    @synchronized (self) {
        NSTimeInterval now = NSDate.timeIntervalSinceReferenceDate;
        for (NSString *key in [_clients.allKeys copy]) {
            NSMutableDictionary *client = _clients[key];
            if (VeritasClientExpired(client, now)) { [_clients removeObjectForKey:key]; continue; }
            if (![client[@"connected"] boolValue]) continue;
            NSMutableArray *queue = client[@"queue"];
            if (queue.count >= 4096) {
                // Disconnect slow clients; never silently deliver a partial battle stream.
                [_clients removeObjectForKey:key]; continue;
            }
            [queue addObject:packet];
        }
    }
}
- (NSString *)poll:(NSString *)sid {
    @synchronized (self) {
        NSMutableDictionary *client = _clients[sid];
        if (!client) return nil;
        NSTimeInterval now = NSDate.timeIntervalSinceReferenceDate;
        if (VeritasClientExpired(client, now)) { [_clients removeObjectForKey:sid]; return nil; }
        client[@"seen"] = @(now);
        if ([client[@"websocket"] boolValue] || [client[@"probe"] boolValue]) return @"6";
        NSMutableArray *queue = client[@"queue"];
        NSString *payload = queue.count ? [queue componentsJoinedByString:@"\x1e"] : @"6";
        if (!queue.count && now - [client[@"lastPing"] doubleValue] >= 25 && ![client[@"pingSent"] doubleValue]) {
            payload = @"2"; client[@"pingSent"] = client[@"lastPing"] = @(now);
        }
        [queue removeAllObjects];
        return payload;
    }
}
- (BOOL)receivePacket:(NSString *)packet session:(NSString *)sid {
    @synchronized (self) {
        NSMutableDictionary *client = _clients[sid];
        if (!client || !packet.length) return NO;
        client[@"seen"] = @(NSDate.timeIntervalSinceReferenceDate);
        if ([packet hasPrefix:@"40/"]) {
            NSString *name = [[packet substringFromIndex:2] componentsSeparatedByString:@","].firstObject;
            [client[@"queue"] addObject:[NSString stringWithFormat:@"44%@,%@", name, VeritasJSON(@{@"message": @"Invalid namespace"})]];
        } else if ([packet hasPrefix:@"40"]) {
            NSString *auth = [packet substringFromIndex:2];
            id object = auth.length ? [NSJSONSerialization JSONObjectWithData:[auth dataUsingEncoding:NSUTF8StringEncoding] options:0 error:NULL] : nil;
            if (auth.length && ![object isKindOfClass:NSDictionary.class]) return NO;
            if (![client[@"connected"] boolValue]) {
                client[@"connected"] = @YES;
                [client[@"queue"] addObject:[@"40" stringByAppendingString:VeritasJSON(@{@"sid": sid})]];
                [client[@"queue"] addObject:[@"42" stringByAppendingString:VeritasJSON(@[@"Connected", @{@"version": @"0.2.58"}])]];
            }
        } else if ([packet isEqual:@"1"] || [packet isEqual:@"41"]) {
            [_clients removeObjectForKey:sid]; return NO;
        } else if ([packet isEqual:@"3"]) client[@"pingSent"] = @0;
        else if (![packet hasPrefix:@"42"]) return NO;
        return YES;
    }
}
- (NSString *)newSession {
    @synchronized (self) {
        for (NSString *key in [_clients.allKeys copy]) if (VeritasClientExpired(_clients[key], NSDate.timeIntervalSinceReferenceDate)) [_clients removeObjectForKey:key];
        if (_clients.count >= 8) return nil;
        NSString *sid = NSUUID.UUID.UUIDString;
        _clients[sid] = [@{@"queue": [NSMutableArray array], @"seen": @(NSDate.timeIntervalSinceReferenceDate), @"lastPing": @(NSDate.timeIntervalSinceReferenceDate), @"connected": @NO} mutableCopy];
        return sid;
    }
}
- (NSString *)openPacket:(NSString *)sid upgrades:(BOOL)upgrades {
    return [@"0" stringByAppendingString:VeritasJSON(@{@"sid": sid, @"upgrades": upgrades ? @[@"websocket"] : @[],
        @"pingInterval": @25000, @"pingTimeout": @20000, @"maxPayload": @65536})];
}
- (void)websocket:(int)socket headers:(NSDictionary *)headers session:(NSString *)existing {
    NSString *key = headers[@"sec-websocket-key"];
    NSData *decoded = key ? [[NSData alloc] initWithBase64EncodedString:key options:0] : nil;
    BOOL connectionUpgrade = NO;
    for (NSString *token in [headers[@"connection"] componentsSeparatedByString:@","]) if ([[token stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet] caseInsensitiveCompare:@"upgrade"] == NSOrderedSame) connectionUpgrade = YES;
    NSString *sid = existing;
    BOOL accepted = [headers[@"upgrade"] length] && decoded.length == 16 && [headers[@"sec-websocket-version"] isEqual:@"13"] &&
        [headers[@"upgrade"] caseInsensitiveCompare:@"websocket"] == NSOrderedSame && connectionUpgrade;
    @synchronized (self) {
        if (accepted && existing) accepted = _clients[existing] && !_clients[existing][@"ws_socket"] && !VeritasClientExpired(_clients[existing], NSDate.timeIntervalSinceReferenceDate);
        if (accepted && !sid) sid = [self newSession];
        accepted = accepted && sid != nil;
        if (accepted) _clients[sid][@"ws_socket"] = @(socket);
    }
    if (!accepted) {
        VeritasSendBytes(socket, [@"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding]);
        close(socket); return;
    }
    NSString *handshake = [NSString stringWithFormat:@"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %@\r\n\r\n", VeritasWebSocketAccept(key)];
    BOOL live = VeritasSendBytes(socket, [handshake dataUsingEncoding:NSUTF8StringEncoding]), promoted = !existing;
    if (!existing && live) {
        @synchronized (self) { _clients[sid][@"websocket"] = @YES; }
        live = VeritasSendText(socket, [self openPacket:sid upgrades:NO]);
    }
    NSMutableData *input = [NSMutableData data], *message = nil;
    NSTimeInterval lastPing = NSDate.timeIntervalSinceReferenceDate, pingSent = 0;
    while (live) { @autoreleasepool {
        NSArray *outgoing = nil;
        @synchronized (self) {
            NSMutableDictionary *client = _clients[sid];
            if (!client) live = NO;
            else if (promoted) { outgoing = [client[@"queue"] copy]; [client[@"queue"] removeAllObjects]; }
        }
        if (!live) break;
        for (NSString *packet in outgoing) if (!VeritasSendText(socket, packet)) { live = NO; break; }
        if (!live) break;
        NSTimeInterval now = NSDate.timeIntervalSinceReferenceDate;
        if ((!promoted && now - lastPing > 20) || (pingSent && now - pingSent > 20)) break;
        if (promoted && !pingSent && now - lastPing >= 25) {
            if (!VeritasSendText(socket, @"2")) break;
            pingSent = lastPing = now;
        }
        struct pollfd descriptor = {.fd = socket, .events = POLLIN};
        int ready = poll(&descriptor, 1, 50);
        if (ready < 0) { if (errno == EINTR) continue; break; }
        if (!ready) continue;
        if (!(descriptor.revents & POLLIN)) break;
        uint8_t bytes[4096]; ssize_t count = recv(socket, bytes, sizeof(bytes), 0);
        if (count <= 0) break;
        [input appendBytes:bytes length:(NSUInteger)count];
        if (input.length > 131100) break;
        while (live) {
            NSData *payload = nil; uint8_t opcode = 0; BOOL final = NO;
            int frame = VeritasReadFrame(input, &payload, &opcode, &final);
            if (!frame) break;
            if (frame < 0) { const uint8_t code[] = {3, 234}; VeritasSendFrame(socket, 8, [NSData dataWithBytes:code length:2]); live = NO; break; }
            if (opcode == 8) { VeritasSendFrame(socket, 8, payload); live = NO; break; }
            if (opcode == 9) { live = VeritasSendFrame(socket, 10, payload); continue; }
            if (opcode == 10) continue;
            if ((opcode == 1 && message) || (opcode == 0 && !message) || (opcode != 1 && opcode != 0)) { live = NO; break; }
            if (opcode == 1) message = [NSMutableData data];
            if (message.length + payload.length > 65536) { live = NO; break; }
            [message appendData:payload];
            if (!final) continue;
            NSString *packet = [[NSString alloc] initWithData:message encoding:NSUTF8StringEncoding]; message = nil;
            if (!packet) { live = NO; break; }
            if ([packet isEqual:@"2probe"] && !promoted) {
                @synchronized (self) { _clients[sid][@"probe"] = @YES; }
                live = VeritasSendText(socket, @"3probe");
            } else if ([packet isEqual:@"5"] && !promoted) {
                @synchronized (self) {
                    if (![_clients[sid][@"probe"] boolValue]) { live = NO; break; }
                    _clients[sid][@"websocket"] = @YES;
                }
                promoted = YES; lastPing = now;
            } else if (promoted) {
                if ([packet isEqual:@"3"]) pingSent = 0;
                live = [self receivePacket:packet session:sid];
            } else live = NO;
        }
    } }
    @synchronized (self) {
        if ([_clients[sid][@"ws_socket"] intValue] == socket) {
            if (promoted) [_clients removeObjectForKey:sid];
            else { [_clients[sid] removeObjectForKey:@"ws_socket"]; [_clients[sid] removeObjectForKey:@"probe"]; }
        }
    }
    close(socket);
}
- (void)serve:(int)socket {
    @autoreleasepool {
        struct timeval timeout = {5, 0};
        setsockopt(socket, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        setsockopt(socket, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        int noPipe = 1; setsockopt(socket, SOL_SOCKET, SO_NOSIGPIPE, &noPipe, sizeof(noPipe));
        NSMutableData *request = [NSMutableData data]; NSRange separator = NSMakeRange(NSNotFound, 0);
        NSData *marker = [@"\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding];
        char buffer[4096];
        while (request.length < 65536 && separator.location == NSNotFound) {
            ssize_t count = recv(socket, buffer, sizeof(buffer), 0);
            if (count <= 0) { close(socket); return; }
            [request appendBytes:buffer length:(NSUInteger)count];
            separator = [request rangeOfData:marker options:0 range:NSMakeRange(0, request.length)];
        }
        if (separator.location == NSNotFound) { close(socket); return; }
        NSString *head = [[NSString alloc] initWithData:[request subdataWithRange:NSMakeRange(0, separator.location)] encoding:NSUTF8StringEncoding];
        NSArray *lines = [head componentsSeparatedByString:@"\r\n"];
        NSArray *first = [lines.firstObject componentsSeparatedByString:@" "];
        if (first.count != 3) { close(socket); return; }
        NSMutableDictionary *headers = [NSMutableDictionary dictionary];
        for (NSString *line in lines) {
            NSRange colon = [line rangeOfString:@":"];
            if (colon.location != NSNotFound) headers[[[line substringToIndex:colon.location] lowercaseString]] =
                [[line substringFromIndex:colon.location + 1] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
        }
        NSString *lengthHeader = headers[@"content-length"];
        NSCharacterSet *nonDigits = [NSCharacterSet characterSetWithCharactersInString:@"0123456789"].invertedSet;
        if (lengthHeader && (!lengthHeader.length || [lengthHeader rangeOfCharacterFromSet:nonDigits].location != NSNotFound)) {
            VeritasSendBytes(socket, [@"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding]);
            close(socket); return;
        }
        NSInteger length = lengthHeader ? [lengthHeader integerValue] : 0;
        if (length < 0 || length > 65536) { close(socket); return; }
        NSUInteger bodyStart = NSMaxRange(separator);
        while (request.length < bodyStart + (NSUInteger)length) {
            ssize_t count = recv(socket, buffer, MIN(sizeof(buffer), bodyStart + (NSUInteger)length - request.length), 0);
            if (count <= 0) { close(socket); return; }
            [request appendBytes:buffer length:(NSUInteger)count];
        }
        NSString *body = length ? [[NSString alloc] initWithData:[request subdataWithRange:NSMakeRange(bodyStart, (NSUInteger)length)] encoding:NSUTF8StringEncoding] : @"";
        if (!body) {
            VeritasSendBytes(socket, [@"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding]);
            close(socket); return;
        }
        NSURLComponents *url = [NSURLComponents componentsWithString:[@"http://localhost" stringByAppendingString:first[1]]];
        NSMutableDictionary *query = [NSMutableDictionary dictionary];
        for (NSURLQueryItem *item in url.queryItems) if (item.value) query[item.name] = item.value;
        NSString *sid = query[@"sid"], *payload = @"Unknown endpoint";
        int status = 404;
        BOOL socketPath = [url.path isEqualToString:@"/socket.io/"];
        if (socketPath && [query[@"EIO"] isEqual:@"4"] && [query[@"transport"] isEqual:@"websocket"] && [first[0] isEqual:@"GET"]) {
            [self websocket:socket headers:headers session:sid]; return;
        }
        BOOL endpoint = socketPath && [query[@"EIO"] isEqual:@"4"] && [query[@"transport"] isEqual:@"polling"];
        if (socketPath && !endpoint) status = 400;
        if ([first[0] isEqual:@"OPTIONS"]) { payload = @""; status = 200; }
        else if (endpoint && [first[0] isEqual:@"GET"] && !sid) {
            sid = [self newSession];
            if (sid) { payload = [self openPacket:sid upgrades:YES]; status = 200; }
            else { status = 503; payload = @"Client limit reached"; }
        } else if (endpoint && [first[0] isEqual:@"GET"] && sid) {
            NSMutableDictionary *reader = nil;
            @synchronized (self) {
                reader = _clients[sid];
                if ([reader[@"reading"] boolValue]) { [_clients removeObjectForKey:sid]; reader = nil; }
                else reader[@"reading"] = @YES;
            }
            // Bounded long polling also wakes when a WebSocket probe needs a noop.
            for (unsigned attempt = 0; reader && attempt < 100; attempt++) {
                BOOL ready;
                @synchronized (self) { ready = !_clients[sid] || [_clients[sid][@"queue"] count] > 0 ||
                    [_clients[sid][@"probe"] boolValue] || [_clients[sid][@"websocket"] boolValue] ||
                    VeritasClientExpired(_clients[sid], NSDate.timeIntervalSinceReferenceDate); }
                if (ready) break;
                [NSThread sleepForTimeInterval:0.05];
            }
            payload = reader ? [self poll:sid] : nil; status = payload ? 200 : 400;
            @synchronized (self) { reader[@"reading"] = @NO; }
            if (!payload) payload = @"Unknown or overlapping polling session";
        } else if (endpoint && [first[0] isEqual:@"POST"] && sid) {
            @synchronized (self) {
                NSMutableDictionary *client = _clients[sid];
                if (client && ![client[@"writing"] boolValue]) {
                    client[@"writing"] = @YES;
                    client[@"seen"] = @(NSDate.timeIntervalSinceReferenceDate);
                    for (NSString *packet in [body componentsSeparatedByString:@"\x1e"]) {
                        if (![self receivePacket:packet session:sid]) { [_clients removeObjectForKey:sid]; break; }
                    }
                    payload = @"ok"; status = 200;
                } else { [_clients removeObjectForKey:sid]; status = 400; payload = @"Unknown or overlapping session"; }
            }
        } else if ([url.path isEqual:@"/"]) {
            payload = @"Veritas PlayCover API. Socket.IO v4: /socket.io/?EIO=4&transport=polling"; status = 200;
        }
        NSData *content = [payload dataUsingEncoding:NSUTF8StringEncoding];
        NSString *response = [NSString stringWithFormat:@"HTTP/1.1 %d %@\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Length: %lu\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type\r\nConnection: close\r\n\r\n", status, status == 200 ? @"OK" : @"Error", (unsigned long)content.length];
        NSMutableData *reply = [[response dataUsingEncoding:NSUTF8StringEncoding] mutableCopy]; [reply appendData:content];
        VeritasSendBytes(socket, reply);
        if (endpoint && sid && [first[0] isEqual:@"POST"]) @synchronized (self) { _clients[sid][@"writing"] = @NO; }
        close(socket);
    }
}
- (void)start {
    if (_listener >= 0) return;
    int listener = socket(AF_INET, SOCK_STREAM, 0), reuse = 1;
    if (listener < 0) { self.status = @"API socket failed"; return; }
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    struct sockaddr_in address = {.sin_len = sizeof(address), .sin_family = AF_INET,
        .sin_port = htons(1305), .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) || listen(listener, 8)) {
        self.status = [NSString stringWithFormat:@"API unavailable: %s", strerror(errno)]; close(listener); return;
    }
    _listener = listener; self.status = @"API 127.0.0.1:1305 · Socket.IO v4";
    _source = dispatch_source_create(DISPATCH_SOURCE_TYPE_READ, (uintptr_t)listener, 0, dispatch_get_global_queue(QOS_CLASS_UTILITY, 0));
    __weak VeritasServer *weakSelf = self;
    dispatch_source_set_event_handler(_source, ^{
        int connection = accept(listener, NULL, NULL);
        if (connection < 0) return;
        VeritasServer *server = weakSelf;
        @synchronized (server) {
            if (!server || server->_connections >= 16) { close(connection); return; }
            server->_connections++;
        }
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
            @try { [server serve:connection]; }
            @finally { @synchronized (server) { server->_connections--; } }
        });
    });
    dispatch_resume(_source);
}
@end
