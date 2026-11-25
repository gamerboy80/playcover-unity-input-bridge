#import "Assets.h"
static UIImage *VeritasPortrait(NSString *identifier, BOOL enemy) {
    static NSCache *cache;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ cache = [NSCache new]; cache.countLimit = 64; });
    NSString *key = [NSString stringWithFormat:@"%@/%@", enemy ? @"enemies" : @"avatars", identifier];
    UIImage *image = VeritasCachedPortrait(key);
    if (image) return image;
    id cached = [cache objectForKey:key];
    if (cached == NSNull.null) return nil;
    if (cached) return cached;
    NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSURL *file = [documents URLByAppendingPathComponent:[NSString stringWithFormat:@"Veritas/Portraits/%@.png", key]];
    image = [UIImage imageWithContentsOfFile:file.path];
    [cache setObject:image ?: NSNull.null forKey:key];
    return image;
}
static UIColor *VeritasCharacterColor(NSUInteger index) {
    static const unsigned colors[] = {0xff6384, 0x36a2eb, 0xffce56, 0x4bc0c0, 0x9966ff, 0xff9f40, 0xe7e9ed, 0x66ff66};
    unsigned rgb = colors[index % 8];
    return [UIColor colorWithRed:(rgb >> 16) / 255.0 green:((rgb >> 8) & 255) / 255.0 blue:(rgb & 255) / 255.0 alpha:1];
}
static NSString *VeritasNumber(double value) {
    if (value >= 1000000) return [NSString stringWithFormat:@"%.1fM", value / 1000000];
    if (value >= 1000) return [NSString stringWithFormat:@"%.1fK", value / 1000];
    return [NSString stringWithFormat:@"%.0f", value];
}

@interface VeritasDamageCharts : UIView
@property(nonatomic, copy) NSDictionary *series;
@property(nonatomic, copy) NSString *kind;
@property(nonatomic, strong) UIColor *textColor;
@property(nonatomic) CGFloat textSize;
@property(nonatomic) CGFloat pieOpacity;
@property(nonatomic) BOOL dpav;
@property(nonatomic) BOOL avAxis;
@property(nonatomic) BOOL pie;
@property(nonatomic) BOOL showLegend;
@property(nonatomic) BOOL showTable;
@property(nonatomic, copy) NSString *selectedOwner;
@end
@implementation VeritasDamageCharts
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self = [super initWithFrame:frame])) _pieOpacity = 0.8;
    return self;
}
- (void)setSeries:(NSDictionary *)series { _series = [series copy]; [self setNeedsDisplay]; }
- (void)text:(NSString *)text rect:(CGRect)rect bold:(BOOL)bold color:(UIColor *)color {
    NSMutableParagraphStyle *paragraph = [NSMutableParagraphStyle new];
    paragraph.lineBreakMode = NSLineBreakByTruncatingTail;
    [text drawInRect:rect withAttributes:@{NSFontAttributeName: [UIFont monospacedDigitSystemFontOfSize:self.textSize weight:bold ? UIFontWeightSemibold : UIFontWeightRegular],
        NSForegroundColorAttributeName: color ?: self.textColor ?: UIColor.whiteColor, NSParagraphStyleAttributeName: paragraph}];
}
- (void)drawBars:(NSDictionary *)amounts names:(NSDictionary *)names rect:(CGRect)rect {
    NSArray *keys = [amounts keysSortedByValueUsingComparator:^NSComparisonResult(NSNumber *a, NSNumber *b) { return [b compare:a]; }];
    double max = MAX([amounts[keys.firstObject] doubleValue], 1), total = 0;
    for (NSNumber *value in amounts.allValues) total += value.doubleValue;
    CGFloat rowHeight = MAX(38, self.textSize * 2 + 12);
    for (NSUInteger index = 0; index < keys.count; index++) {
        CGFloat y = rect.origin.y + rowHeight * index;
        if (y + rowHeight > CGRectGetMaxY(rect)) break;
        NSString *key = keys[index], *name = names[key] ?: key;
        double value = [amounts[key] doubleValue];
        UIColor *color = VeritasCharacterColor([[self.series[@"lineup"] valueForKey:@"id"] indexOfObject:@(key.intValue)]);
        if ([self.kind isEqual:@"types"]) color = VeritasCharacterColor(index);
        [color setFill];
        [[UIBezierPath bezierPathWithRoundedRect:CGRectMake(rect.origin.x, y + 2, 28, 28) cornerRadius:5] fill];
        UIImage *portrait = [self.kind isEqual:@"types"] ? nil : VeritasPortrait(key, NO);
        if (portrait) [portrait drawInRect:CGRectMake(rect.origin.x, y + 2, 28, 28)];
        else [self text:[[name substringToIndex:MIN(name.length, 2)] uppercaseString] rect:CGRectMake(rect.origin.x + 3, y + 8, 24, 18) bold:YES color:UIColor.blackColor];
        [self text:name rect:CGRectMake(rect.origin.x + 36, y, MAX(0, rect.size.width - 164), 20) bold:YES color:nil];
        NSString *amount = [NSString stringWithFormat:@"%@ · %.1f%%", VeritasNumber(value), total > 0 ? 100 * value / total : 0];
        [self text:amount rect:CGRectMake(CGRectGetMaxX(rect) - 120, y, 120, 20) bold:NO color:nil];
        CGFloat barX = rect.origin.x + 36, barWidth = rect.size.width - 36;
        [[color colorWithAlphaComponent:0.12] setFill]; UIRectFill(CGRectMake(barX, y + 23, barWidth, 5));
        [color setFill]; UIRectFill(CGRectMake(barX, y + 23, barWidth * value / max, 5));
        if (![self.kind isEqual:@"types"]) {
            double overkill = [self.series[@"overkills"][key] doubleValue];
            if (self.dpav) overkill /= MAX([self.series[@"action_value"] doubleValue], 1);
            overkill = MIN(overkill, value);
            [[UIColor colorWithWhite:0.55 alpha:1] setFill];
            UIRectFill(CGRectMake(barX + barWidth * (value - overkill) / max, y + 23, barWidth * overkill / max, 5));
        }
    }
}
- (void)drawColumns:(NSDictionary *)amounts names:(NSDictionary *)names rect:(CGRect)rect {
    NSArray *keys = [amounts.allKeys sortedArrayUsingSelector:@selector(compare:)];
    if (!keys.count) return;
    double max = MAX([[amounts.allValues valueForKeyPath:@"@max.self"] doubleValue], 1);
    CGFloat step = rect.size.width / keys.count, bottom = CGRectGetMaxY(rect) - self.textSize * 3;
    for (NSUInteger index = 0; index < keys.count; index++) {
        NSString *key = keys[index]; double value = [amounts[key] doubleValue];
        CGFloat height = MAX(0, bottom - rect.origin.y - 25) * value / max;
        CGFloat x = rect.origin.x + step * index + step * 0.15;
        [VeritasCharacterColor(index) setFill]; UIRectFill(CGRectMake(x, bottom - height, step * 0.7, height));
        double overkill = [self.series[@"overkills"][key] doubleValue];
        if (self.dpav) overkill /= MAX([self.series[@"action_value"] doubleValue], 1);
        CGFloat cap = value > 0 ? height * MIN(value, overkill) / value : 0;
        [[UIColor colorWithWhite:0.55 alpha:1] setFill]; UIRectFill(CGRectMake(x, bottom - height, step * 0.7, cap));
        [self text:VeritasNumber(value) rect:CGRectMake(x, bottom - height - 22, step, 20) bold:NO color:nil];
        [self text:names[key] ?: key rect:CGRectMake(x, bottom + 4, step * 0.85, self.textSize * 3) bold:NO color:nil];
    }
}
- (void)drawPie:(NSDictionary *)amounts names:(NSDictionary *)names rect:(CGRect)rect {
    NSArray *keys = [amounts.allKeys sortedArrayUsingSelector:@selector(compare:)];
    double total = [[amounts.allValues valueForKeyPath:@"@sum.self"] doubleValue];
    CGFloat diameter = MIN(rect.size.width * (self.showLegend ? 0.48 : 0.9), rect.size.height - 6);
    CGPoint center = CGPointMake(rect.origin.x + diameter * 0.5, rect.origin.y + diameter * 0.5);
    double angle = -M_PI_2;
    for (NSUInteger index = 0; index < keys.count; index++) {
        double value = [amounts[keys[index]] doubleValue], next = angle + (total > 0 ? value / total * 2 * M_PI : 0);
        UIColor *color = VeritasCharacterColor(index);
        UIBezierPath *slice = [UIBezierPath bezierPath]; [slice moveToPoint:center];
        [slice addArcWithCenter:center radius:diameter * 0.46 startAngle:angle endAngle:next clockwise:YES];
        [slice closePath]; [[color colorWithAlphaComponent:self.pieOpacity] setFill]; [slice fill];
        if (self.showLegend) {
            CGFloat y = rect.origin.y + 22 * index;
            [color setFill]; UIRectFill(CGRectMake(rect.origin.x + diameter + 4, y + 4, 8, 8));
            [self text:[NSString stringWithFormat:@"%@ %.0f%%", names[keys[index]] ?: keys[index], total > 0 ? value / total * 100 : 0]
                rect:CGRectMake(rect.origin.x + diameter + 18, y, rect.size.width - diameter - 18, 21) bold:NO color:nil];
        }
        angle = next;
    }
}
- (void)drawGraph:(CGRect)rect {
    NSMutableArray *turns = [self.series[self.avAxis ? @"av_history" : @"turn_history"] mutableCopy];
    NSDictionary *current = self.series[@"current_turn"];
    if ([current[@"turn"] unsignedIntValue] > [turns.lastObject[@"turn"] unsignedIntValue]) [turns addObject:current];
    if (!turns.count) { [self text:@"Waiting for completed turns" rect:rect bold:NO color:nil]; return; }
    CGFloat bottom = CGRectGetMaxY(rect) - 24, top = rect.origin.y + 12;
    double xmax = self.avAxis ? MAX(1, [turns.lastObject[@"action_value"] doubleValue]) : turns.count;
    NSDictionary *owners = self.series[@"avatars"];
    double peak = 1;
    for (NSDictionary *turn in turns) for (NSNumber *value in [turn[@"damage_by_owner"] allValues]) peak = MAX(peak, value.doubleValue);
    [[self.textColor colorWithAlphaComponent:0.15] setStroke];
    for (unsigned grid = 0; grid <= 4; grid++) {
        CGFloat y = top + (bottom - top) * grid / 4;
        UIBezierPath *path = [UIBezierPath bezierPath]; [path moveToPoint:CGPointMake(rect.origin.x, y)];
        [path addLineToPoint:CGPointMake(CGRectGetMaxX(rect), y)]; [path stroke];
    }
    NSUInteger colorIndex = 0;
    for (NSString *owner in [owners.allKeys sortedArrayUsingSelector:@selector(compare:)]) {
        UIColor *color = VeritasCharacterColor(colorIndex++);
        UIBezierPath *line = [UIBezierPath bezierPath]; BOOL first = YES;
        // Keep rendering bounded while retaining every point in exports.
        NSUInteger step = MAX(1, turns.count / MAX((NSUInteger)rect.size.width, 1));
        for (NSUInteger index = 0; index < turns.count; index += step) {
            NSDictionary *turn = turns[index];
            double x = self.avAxis ? [turn[@"action_value"] doubleValue] : index + 1;
            double value = [turn[@"damage_by_owner"][owner] doubleValue];
            CGPoint point = CGPointMake(rect.origin.x + rect.size.width * x / xmax, bottom - (bottom - top) * value / peak);
            if (first) [line moveToPoint:point]; else [line addLineToPoint:point]; first = NO;
        }
        [color setStroke]; line.lineWidth = 1.5; [line stroke];
    }
    [self text:[NSString stringWithFormat:@"0                       %.0f %@", xmax, self.avAxis ? @"AV" : @"turns"]
        rect:CGRectMake(rect.origin.x, bottom + 4, rect.size.width, 20) bold:NO color:nil];
    [self text:VeritasNumber(peak) rect:CGRectMake(rect.origin.x, top, 80, 20) bold:NO color:nil];
}
- (void)drawRect:(CGRect)rect {
    [super drawRect:rect];
    NSDictionary *owners = self.series[@"avatars"] ?: @{}, *names = self.series[@"names"] ?: @{};
    if ([self.kind isEqual:@"graph"]) { [self drawGraph:rect]; return; }
    if ([self.kind isEqual:@"types"]) {
        NSMutableDictionary *totals = [NSMutableDictionary dictionary];
        NSDictionary *all = self.series[@"attackDamage"];
        for (NSString *owner in all) {
            if (self.selectedOwner && ![owner isEqual:self.selectedOwner]) continue;
            for (NSString *type in all[owner]) totals[type] = @([totals[type] doubleValue] + [all[owner][type] doubleValue]);
        }
        if (!totals.count) { [self text:@"Waiting for damage" rect:rect bold:NO color:nil]; return; }
        if (self.pie) {
            CGRect pieRect = rect; pieRect.size.height *= self.showTable ? 0.55 : 1;
            [self drawPie:totals names:@{} rect:pieRect];
            if (self.showTable) [self drawBars:totals names:@{} rect:CGRectMake(0, CGRectGetMaxY(pieRect) + 8, rect.size.width, rect.size.height - pieRect.size.height - 8)];
        } else [self drawBars:totals names:@{} rect:rect];
    } else if ([self.kind isEqual:@"distribution"]) [self drawPie:owners names:names rect:rect];
    else {
        NSMutableDictionary *values = [owners mutableCopy];
        if (self.dpav) {
            double av = [self.series[@"action_value"] doubleValue];
            for (NSString *key in values.allKeys) values[key] = @([values[key] doubleValue] / (av > 0 ? av : 1));
        }
        if ([self.kind isEqual:@"bars"]) [self drawColumns:values names:names rect:rect];
        else [self drawBars:values names:names rect:rect];
    }
}
@end
