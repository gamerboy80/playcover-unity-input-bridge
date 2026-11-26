#import "Server.h"
#include <assert.h>

static NSString *RequestData(VeritasServer *server, NSData *data) {
    int pair[2]; assert(socketpair(AF_UNIX, SOCK_STREAM, 0, pair) == 0);
    int incoming = pair[0];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ [server serve:incoming]; });
    assert(send(pair[1], data.bytes, data.length, 0) == (ssize_t)data.length);
    NSMutableData *response = [NSMutableData data]; char bytes[4096]; ssize_t count;
    while ((count = recv(pair[1], bytes, sizeof(bytes), 0)) > 0) [response appendBytes:bytes length:(NSUInteger)count];
    close(pair[1]);
    return [[NSString alloc] initWithData:response encoding:NSUTF8StringEncoding];
}
static NSString *Request(VeritasServer *server, NSString *request) {
    return RequestData(server, [request dataUsingEncoding:NSUTF8StringEncoding]);
}
static NSData *ReadExact(int socket, NSUInteger length) {
    NSMutableData *data = [NSMutableData dataWithLength:length]; NSUInteger read = 0;
    while (read < length) {
        ssize_t count = recv(socket, (char *)data.mutableBytes + read, length - read, 0);
        assert(count > 0); read += (NSUInteger)count;
    }
    return data;
}
static NSData *ServerFrame(int socket, uint8_t *opcode) {
    NSData *head = ReadExact(socket, 2); const uint8_t *bytes = head.bytes;
    assert((bytes[0] & 0x80) && !(bytes[1] & 0x80)); *opcode = bytes[0] & 15;
    uint64_t length = bytes[1] & 127;
    if (length == 126 || length == 127) {
        NSData *size = ReadExact(socket, length == 126 ? 2 : 8); length = 0;
        for (NSUInteger index = 0; index < size.length; index++) length = length << 8 | ((const uint8_t *)size.bytes)[index];
    }
    assert(length <= 1024 * 1024); return ReadExact(socket, (NSUInteger)length);
}
static NSString *ServerText(int socket) {
    uint8_t opcode; NSData *data = ServerFrame(socket, &opcode); assert(opcode == 1);
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
}
static void ClientFrame(int socket, uint8_t opcode, BOOL final, NSData *payload) {
    assert(payload.length <= 65535);
    NSMutableData *frame = [NSMutableData data]; uint8_t first = opcode | (final ? 0x80 : 0), size = 0x80 | (payload.length < 126 ? (uint8_t)payload.length : 126);
    [frame appendBytes:&first length:1]; [frame appendBytes:&size length:1];
    if (payload.length >= 126) { uint8_t extended[] = {(uint8_t)(payload.length >> 8), (uint8_t)payload.length}; [frame appendBytes:extended length:2]; }
    const uint8_t mask[] = {1, 2, 3, 4}; [frame appendBytes:mask length:4];
    for (NSUInteger index = 0; index < payload.length; index++) { uint8_t byte = ((const uint8_t *)payload.bytes)[index] ^ mask[index % 4]; [frame appendBytes:&byte length:1]; }
    assert(VeritasSendBytes(socket, frame));
}
static void ClientText(int socket, NSString *text) { ClientFrame(socket, 1, YES, [text dataUsingEncoding:NSUTF8StringEncoding]); }
static int WebSocket(VeritasServer *server, NSString *sid, BOOL expected) {
    int pair[2]; assert(socketpair(AF_UNIX, SOCK_STREAM, 0, pair) == 0);
    int incoming = pair[0];
    struct timeval timeout = {2, 0}; setsockopt(pair[1], SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ [server serve:incoming]; });
    NSString *request = [NSString stringWithFormat:@"GET /socket.io/?EIO=4&transport=websocket%@ HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: keep-alive, Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n", sid ? [@"&sid=" stringByAppendingString:sid] : @""];
    assert(VeritasSendBytes(pair[1], [request dataUsingEncoding:NSUTF8StringEncoding]));
    NSMutableData *head = [NSMutableData data]; NSData *end = [@"\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding];
    while ([head rangeOfData:end options:0 range:NSMakeRange(0, head.length)].location == NSNotFound) {
        [head appendData:ReadExact(pair[1], 1)]; assert(head.length < 4096);
    }
    NSString *response = [[NSString alloc] initWithData:head encoding:NSUTF8StringEncoding];
    assert([response hasPrefix:expected ? @"HTTP/1.1 101" : @"HTTP/1.1 400"]);
    if (expected) assert([response containsString:@"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo="]);
    return pair[1];
}
static void CloseWebSocket(int socket) {
    const uint8_t normal[] = {3, 232}; ClientFrame(socket, 8, YES, [NSData dataWithBytes:normal length:2]);
    uint8_t opcode; assert(ServerFrame(socket, &opcode).length == 2 && opcode == 8);
    uint8_t byte; assert(recv(socket, &byte, 1, 0) == 0); close(socket);
}

int main(void) {
    @autoreleasepool {
        VeritasServer *server = [VeritasServer new];
        NSString *response = Request(server, @"GET /socket.io/?EIO=4&transport=polling HTTP/1.1\r\nHost: localhost\r\n\r\n");
        assert([response hasPrefix:@"HTTP/1.1 200"]);
        NSString *body = [response componentsSeparatedByString:@"\r\n\r\n"].lastObject;
        assert([body hasPrefix:@"0"]);
        NSDictionary *open = [NSJSONSerialization JSONObjectWithData:[[body substringFromIndex:1] dataUsingEncoding:NSUTF8StringEncoding] options:0 error:NULL];
        NSString *sid = open[@"sid"]; assert(sid.length && [open[@"upgrades"] isEqual:@[@"websocket"]]);
        response = Request(server, [NSString stringWithFormat:@"POST /socket.io/?EIO=4&transport=polling&sid=%@ HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n40", sid]);
        assert([response hasSuffix:@"ok"]);
        [server publish:@"OnDamage" data:@{@"damage": @100}];
        response = Request(server, [NSString stringWithFormat:@"GET /socket.io/?EIO=4&transport=polling&sid=%@ HTTP/1.1\r\nHost: localhost\r\n\r\n", sid]);
        body = [response componentsSeparatedByString:@"\r\n\r\n"].lastObject;
        NSArray *packets = [body componentsSeparatedByString:@"\x1e"];
        assert(packets.count == 3 && [packets[0] hasPrefix:@"40"]);
        assert([packets[1] hasPrefix:@"42[\"Connected\""] && [packets[2] hasPrefix:@"42[\"OnDamage\""]);
        response = Request(server, @"GET /socket.io/?EIO=4&transport=polling&sid=missing HTTP/1.1\r\nHost: localhost\r\n\r\n");
        assert([response hasPrefix:@"HTTP/1.1 400"]);
        response = Request(server, @"GET /not-an-endpoint HTTP/1.1\r\nHost: localhost\r\n\r\n");
        assert([response hasPrefix:@"HTTP/1.1 404"]);
        response = Request(server, @"POST /socket.io/?EIO=4&transport=polling HTTP/1.1\r\nContent-Length: 999999\r\n\r\n");
        assert(response.length == 0);
        response = Request(server, @"POST /socket.io/?EIO=4&transport=polling HTTP/1.1\r\nContent-Length: 10abc\r\n\r\n");
        assert([response hasPrefix:@"HTTP/1.1 400"]);
        response = Request(server, @"POST /socket.io/?EIO=4&transport=polling HTTP/1.1\r\nContent-Length: -5\r\n\r\n");
        assert([response hasPrefix:@"HTTP/1.1 400"]);
        NSMutableData *badUTF8 = [[@"POST /socket.io/?EIO=4&transport=polling HTTP/1.1\r\nContent-Length: 2\r\n\r\n" dataUsingEncoding:NSUTF8StringEncoding] mutableCopy];
        const uint8_t invalidBytes[] = {0xff, 0xfe};
        [badUTF8 appendBytes:invalidBytes length:sizeof(invalidBytes)];
        response = RequestData(server, badUTF8);
        assert([response hasPrefix:@"HTTP/1.1 400"]);
        int ws = WebSocket(server, nil, YES);
        NSString *hello = ServerText(ws); assert([hello hasPrefix:@"0"]);
        NSDictionary *wsOpen = [NSJSONSerialization JSONObjectWithData:[[hello substringFromIndex:1] dataUsingEncoding:NSUTF8StringEncoding] options:0 error:NULL];
        NSString *auth = [@"40" stringByAppendingString:VeritasJSON(@{@"padding": [@"x" stringByPaddingToLength:200 withString:@"x" startingAtIndex:0]})];
        NSData *authData = [auth dataUsingEncoding:NSUTF8StringEncoding];
        ClientFrame(ws, 1, NO, [authData subdataWithRange:NSMakeRange(0, 20)]);
        ClientFrame(ws, 9, YES, [@"control-ping" dataUsingEncoding:NSUTF8StringEncoding]);
        uint8_t opcode; NSData *pong = ServerFrame(ws, &opcode);
        assert(opcode == 10 && [[[NSString alloc] initWithData:pong encoding:NSUTF8StringEncoding] isEqual:@"control-ping"]);
        ClientFrame(ws, 0, YES, [authData subdataWithRange:NSMakeRange(20, authData.length - 20)]);
        assert([ServerText(ws) hasPrefix:@"40"] && [ServerText(ws) hasPrefix:@"42[\"Connected\""]);
        NSString *large = [@"測" stringByPaddingToLength:24000 withString:@"測" startingAtIndex:0];
        [server publish:@"Large" data:@{@"text": large}];
        assert([ServerText(ws) containsString:large]);
        CloseWebSocket(ws);
        response = Request(server, [NSString stringWithFormat:@"GET /socket.io/?EIO=4&transport=polling&sid=%@ HTTP/1.1\r\n\r\n", wsOpen[@"sid"]]);
        assert([response hasPrefix:@"HTTP/1.1 400"]);

        ws = WebSocket(server, sid, YES);
        ClientText(ws, @"2probe"); assert([ServerText(ws) isEqual:@"3probe"]);
        int duplicate = WebSocket(server, sid, NO); close(duplicate);
        response = Request(server, [NSString stringWithFormat:@"GET /socket.io/?EIO=4&transport=polling&sid=%@ HTTP/1.1\r\n\r\n", sid]);
        assert([response hasSuffix:@"6"]);
        ClientText(ws, @"5"); [server publish:@"OnUseSkill" data:@{@"name": @"test"}];
        assert([ServerText(ws) hasPrefix:@"42[\"Large\""]);
        assert([ServerText(ws) hasPrefix:@"42[\"OnUseSkill\""]);
        CloseWebSocket(ws);

        ws = WebSocket(server, nil, YES); (void)ServerText(ws);
        const uint8_t unmasked[] = {0x81, 2, '4', '0'};
        assert(VeritasSendBytes(ws, [NSData dataWithBytes:unmasked length:sizeof(unmasked)]));
        NSData *closed = ServerFrame(ws, &opcode); assert(opcode == 8 && closed.length == 2);
        uint8_t byte; assert(recv(ws, &byte, 1, 0) == 0); close(ws);

        response = Request(server, @"GET /socket.io/?EIO=4&transport=polling HTTP/1.1\r\n\r\n");
        body = [response componentsSeparatedByString:@"\r\n\r\n"].lastObject;
        NSDictionary *newOpen = [NSJSONSerialization JSONObjectWithData:[[body substringFromIndex:1] dataUsingEncoding:NSUTF8StringEncoding] options:0 error:NULL];
        NSString *expiring = newOpen[@"sid"];
        NSMutableDictionary *clients = [server valueForKey:@"clients"];
        clients[expiring][@"lastPing"] = @(NSDate.timeIntervalSinceReferenceDate - 26);
        assert([[server poll:expiring] isEqual:@"2"]);
        clients[expiring][@"pingSent"] = @(NSDate.timeIntervalSinceReferenceDate - 21);
        response = Request(server, [NSString stringWithFormat:@"GET /socket.io/?EIO=4&transport=polling&sid=%@ HTTP/1.1\r\n\r\n", expiring]);
        assert([response hasPrefix:@"HTTP/1.1 400"]);

    }
}
