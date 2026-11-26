#pragma once
#import <Foundation/Foundation.h>

static inline NSString *PluginCSVCell(id value) {
    NSString *text = value == nil || value == NSNull.null ? @"" : [value description];
    // Spreadsheet programs interpret formulas even inside quoted CSV cells.
    if (![value isKindOfClass:NSNumber.class] && text.length &&
        [@"=+-@\t\r" rangeOfString:[text substringToIndex:1]].location != NSNotFound) {
        text = [@"'" stringByAppendingString:text];
    }
    return [NSString stringWithFormat:@"\"%@\"", [text stringByReplacingOccurrencesOfString:@"\"" withString:@"\"\""]];
}
