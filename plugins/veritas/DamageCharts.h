@interface VeritasDamageCharts : UIView
@property(nonatomic, copy) NSDictionary *series;
@property(nonatomic, strong) UIColor *textColor;
@property(nonatomic) CGFloat textSize;
@end

@implementation VeritasDamageCharts
- (void)setSeries:(NSDictionary *)series {
    _series = [series copy];
    [self setNeedsDisplay];
}

- (void)drawRect:(CGRect)rect {
    [super drawRect:rect];
    NSArray<NSNumber *> *values = self.series[@"history"];
    NSDictionary<NSString *, NSNumber *> *avatars = self.series[@"avatars"];
    NSDictionary<NSString *, NSString *> *names = self.series[@"names"];
    NSArray<NSNumber *> *turns = self.series[@"turns"];
    NSDictionary *heading = @{NSFontAttributeName: [UIFont boldSystemFontOfSize:self.textSize + 1],
                              NSForegroundColorAttributeName: self.textColor ?: UIColor.whiteColor};
    NSDictionary *caption = @{NSFontAttributeName: [UIFont monospacedDigitSystemFontOfSize:MAX(10, self.textSize - 1) weight:UIFontWeightRegular],
                              NSForegroundColorAttributeName: self.textColor ?: UIColor.whiteColor};
    if (values.count < 2) {
        [@"Waiting for damage" drawAtPoint:CGPointMake(0, 8) withAttributes:caption];
        return;
    }

    CGFloat width = CGRectGetWidth(self.bounds);
    CGFloat chartY = 44, chartHeight = 78;
    double total = values.lastObject.doubleValue;
    [@"Cumulative damage" drawAtPoint:CGPointZero withAttributes:heading];
    [[NSNumberFormatter localizedStringFromNumber:@(llround(total)) numberStyle:NSNumberFormatterDecimalStyle]
        drawAtPoint:CGPointMake(0, 24) withAttributes:caption];
    UIBezierPath *line = [UIBezierPath bezierPath];
    CGFloat initialY = chartY + chartHeight * (1 - values.firstObject.doubleValue / MAX(total, 1));
    [line moveToPoint:CGPointMake(0, initialY)];
    for (NSUInteger index = 1; index < values.count; ++index) {
        CGFloat x = width * index / (values.count - 1);
        CGFloat y = chartY + chartHeight * (1 - values[index].doubleValue / MAX(total, 1));
        [line addLineToPoint:CGPointMake(x, y)];
    }
    [[UIColor colorWithRed:0.31 green:0.86 blue:0.88 alpha:1] setStroke];
    line.lineWidth = 2;
    [line stroke];
    [@"Latest hits" drawAtPoint:CGPointMake(0, 128) withAttributes:caption];

    [@"Damage by character" drawAtPoint:CGPointMake(0, 151) withAttributes:heading];
    NSArray<NSString *> *keys = [avatars keysSortedByValueUsingComparator:^NSComparisonResult(NSNumber *a, NSNumber *b) {
        return [b compare:a];
    }];
    double largest = MAX(avatars[keys.firstObject].doubleValue, 1);
    UIColor *barColor = [UIColor colorWithRed:0.48 green:0.61 blue:1 alpha:1];
    NSMutableParagraphStyle *truncate = [NSMutableParagraphStyle new];
    truncate.lineBreakMode = NSLineBreakByTruncatingTail;
    NSMutableDictionary *nameStyle = [caption mutableCopy];
    nameStyle[NSParagraphStyleAttributeName] = truncate;
    NSUInteger shown = MIN(keys.count, 6);
    for (NSUInteger index = 0; index < shown; ++index) {
        NSString *key = keys[index];
        CGFloat y = 175 + 19 * index;
        NSString *name = names[key] ?: key;
        double damage = avatars[key].doubleValue;
        NSString *number = [NSNumberFormatter localizedStringFromNumber:@(llround(damage)) numberStyle:NSNumberFormatterDecimalStyle];
        NSString *amount = [NSString stringWithFormat:@"%@ (%.0f%%)", number, 100 * damage / total];
        CGFloat amountWidth = [amount sizeWithAttributes:caption].width;
        CGFloat nameWidth = MIN(width * 0.38, MAX(0, width - amountWidth - 16));
        [name drawInRect:CGRectMake(0, y, nameWidth, 16) withAttributes:nameStyle];
        CGFloat barWidth = MAX(width - amountWidth - nameWidth - 12, 0) * damage / largest;
        [barColor setFill];
        [[UIBezierPath bezierPathWithRoundedRect:CGRectMake(nameWidth + 4, y + 3, barWidth, 9) cornerRadius:3] fill];
        [amount drawAtPoint:CGPointMake(width - amountWidth, y) withAttributes:caption];
    }

    if (turns.count < 2) return;
    CGFloat turnY = 187 + 19 * shown;
    [@"Damage by turn" drawAtPoint:CGPointMake(0, turnY) withAttributes:heading];
    double peak = [[turns valueForKeyPath:@"@max.self"] doubleValue];
    if (peak <= 0) return;
    [[UIColor colorWithRed:0.31 green:0.86 blue:0.88 alpha:1] setFill];
    CGFloat step = width / turns.count;
    for (NSUInteger index = 0; index < turns.count; index++) {
        CGFloat height = 42 * turns[index].doubleValue / peak;
        UIRectFill(CGRectMake(index * step, turnY + 63 - height, MAX(1, step - 2), height));
    }
}
@end
