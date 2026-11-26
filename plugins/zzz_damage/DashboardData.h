#import <Foundation/Foundation.h>
#import "../CSV.h"

static inline NSString *ZZZCSVCell(id value) {
    return PluginCSVCell(value);
}
static inline NSString *ZZZSummaryCSV(NSDictionary *snapshot) {
    NSMutableString *csv = [NSMutableString stringWithString:@"source_id,avatar_id,name,raw_damage,share_percent,raw_dps,game_seconds,session_hits\r\n"];
    double total = [snapshot[@"total"] doubleValue], seconds = [snapshot[@"seconds"] doubleValue];
    for (NSDictionary *source in snapshot[@"sources"]) {
        double damage = [source[@"damage"] doubleValue];
        NSArray *values = @[source[@"id"] ?: @0, source[@"avatar_id"] ?: @0, source[@"name"] ?: @"", @(damage),
            @(total > 0 ? damage / total * 100 : 0), @(seconds > 0 ? damage / seconds : 0),
            @(seconds), snapshot[@"hits"] ?: @0];
        NSMutableArray *cells = [NSMutableArray array];
        for (id value in values) [cells addObject:ZZZCSVCell(value)];
        [csv appendFormat:@"%@\r\n", [cells componentsJoinedByString:@","]];
    }
    return csv;
}
static inline NSURL *ZZZWriteSummary(NSDictionary *snapshot, BOOL csv, NSError **error) {
    NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSDateFormatter *date = [NSDateFormatter new]; date.dateFormat = @"yyyy-MM-dd";
    NSURL *folder = [documents URLByAppendingPathComponent:[@"ZZZDamage/Exports" stringByAppendingPathComponent:[date stringFromDate:NSDate.date]] isDirectory:YES];
    if (![NSFileManager.defaultManager createDirectoryAtURL:folder withIntermediateDirectories:YES attributes:nil error:error]) return nil;
    NSURL *file = [folder URLByAppendingPathComponent:[NSString stringWithFormat:@"battle-%@.%@", NSUUID.UUID.UUIDString, csv ? @"csv" : @"json"]];
    NSData *data = csv ? [ZZZSummaryCSV(snapshot) dataUsingEncoding:NSUTF8StringEncoding] :
        [NSJSONSerialization dataWithJSONObject:snapshot options:NSJSONWritingPrettyPrinted error:error];
    return data && [data writeToURL:file options:NSDataWritingAtomic error:error] ? file : nil;
}
