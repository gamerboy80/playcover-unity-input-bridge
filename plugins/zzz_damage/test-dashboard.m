#import <Foundation/Foundation.h>
#import "DashboardData.h"
#include <assert.h>
int main(void) { @autoreleasepool {
    NSDictionary *data = @{@"total": @100, @"seconds": @2, @"hits": @3,
        @"sources": @[@{@"id": @1, @"avatar_id": @2, @"name": @"=test,\"name\"", @"damage": @75},
                     @{@"id": @0, @"avatar_id": @0, @"name": @"Other", @"damage": @25}]};
    NSString *csv = ZZZSummaryCSV(data);
    assert([csv containsString:@"\"75\",\"75\",\"37.5\""]);
    assert([csv containsString:@"\"'=test,\"\"name\"\"\""]);
    assert([ZZZCSVCell(@(-1)) isEqual:@"\"-1\""]);
    NSMutableDictionary *zero = [data mutableCopy]; zero[@"seconds"] = @0; zero[@"total"] = @0;
    NSString *zeroCSV = ZZZSummaryCSV(zero);
    assert(![zeroCSV containsString:@"nan"] && ![zeroCSV containsString:@"inf"]);
    assert([ZZZCSVCell(nil) isEqual:@"\"\""] && [ZZZCSVCell(NSNull.null) isEqual:@"\"\""]);
    NSString *partialCSV = ZZZSummaryCSV(@{@"sources": @[@{@"damage": @12}]});
    assert([partialCSV containsString:@"\"0\",\"0\",\"\",\"12\",\"0\",\"0\",\"0\",\"0\""]);
} return 0; }
