#import <Foundation/Foundation.h>
#include <CommonCrypto/CommonDigest.h>
#include <sys/socket.h>

static BOOL VeritasSendBytes(int socket, NSData *data) {
    NSUInteger sent = 0;
    while (sent < data.length) {
        ssize_t count = send(socket, (const char *)data.bytes + sent, data.length - sent, 0);
        if (count <= 0) return NO;
        sent += (NSUInteger)count;
    }
    return YES;
}
static NSString *VeritasWebSocketAccept(NSString *key) {
    NSData *input = [[key stringByAppendingString:@"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"] dataUsingEncoding:NSUTF8StringEncoding];
    unsigned char digest[CC_SHA1_DIGEST_LENGTH];
    CC_SHA1(input.bytes, (CC_LONG)input.length, digest);
    return [[NSData dataWithBytes:digest length:sizeof(digest)] base64EncodedStringWithOptions:0];
}
static BOOL VeritasSendFrame(int socket, uint8_t opcode, NSData *payload) {
    uint8_t header[10] = {0x80 | opcode}; NSUInteger size = 2;
    if (payload.length <= 125) header[1] = (uint8_t)payload.length;
    else if (payload.length <= 65535) {
        header[1] = 126; header[2] = (uint8_t)(payload.length >> 8); header[3] = (uint8_t)payload.length; size = 4;
    } else {
        header[1] = 127;
        for (unsigned index = 0; index < 8; index++) header[2 + index] = (uint8_t)((uint64_t)payload.length >> (56 - index * 8));
        size = 10;
    }
    return VeritasSendBytes(socket, [NSData dataWithBytes:header length:size]) && VeritasSendBytes(socket, payload);
}
static BOOL VeritasSendText(int socket, NSString *text) {
    return VeritasSendFrame(socket, 1, [text dataUsingEncoding:NSUTF8StringEncoding]);
}
// Returns one complete masked client frame, zero for a partial frame, or -1 for invalid input.
static int VeritasReadFrame(NSMutableData *input, NSData **payload, uint8_t *opcode, BOOL *final) {
    if (input.length < 2) return 0;
    const uint8_t *bytes = input.bytes;
    if ((bytes[0] & 0x70) || !(bytes[1] & 0x80)) return -1;
    uint64_t length = bytes[1] & 127; NSUInteger offset = 2;
    if (length == 126) {
        if (input.length < 4) return 0;
        length = (uint64_t)bytes[2] << 8 | bytes[3]; offset = 4;
        if (length < 126) return -1;
    } else if (length == 127) {
        if (input.length < 10) return 0;
        length = 0;
        for (unsigned index = 0; index < 8; index++) length = length << 8 | bytes[2 + index];
        offset = 10;
        if (length < 65536) return -1;
    }
    *opcode = bytes[0] & 15; *final = (bytes[0] & 0x80) != 0;
    if ((*opcode == 8 && length == 1) || length > 65536 || ((*opcode & 8) && (!*final || length > 125))) return -1;
    if (input.length < offset + 4 + length) return 0;
    NSMutableData *decoded = [NSMutableData dataWithLength:(NSUInteger)length];
    uint8_t *target = decoded.mutableBytes;
    for (NSUInteger index = 0; index < length; index++) target[index] = bytes[offset + 4 + index] ^ bytes[offset + index % 4];
    *payload = decoded;
    [input replaceBytesInRange:NSMakeRange(0, offset + 4 + (NSUInteger)length) withBytes:NULL length:0];
    return 1;
}
