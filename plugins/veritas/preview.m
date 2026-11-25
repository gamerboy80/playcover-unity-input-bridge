#import <UIKit/UIKit.h>
#import "Telemetry.h"
#import "DamageCharts.h"
#import "OverlayControls.h"
int main(void) { @autoreleasepool {
    VeritasBattle *battle = [VeritasBattle new];
    [battle setLineup:@[@{@"id": @1001, @"name": @"Cipher"}, @{@"id": @1002, @"name": @"Hyacine"}, @{@"id": @1003, @"name": @"Tribbie"}, @{@"id": @1004, @"name": @"Sunday"}]];
    for (unsigned turn = 0; turn < 12; turn++) {
        [battle beginTurnAtActionValue:(turn + 1) * 15 wave:1];
        for (unsigned owner = 1001; owner < 1005; owner++) {
            [battle record:(owner == 1001 ? 135000 : 17000) * (1 + turn % 3) overkill:turn == 11 ? 10000 : 0 owner:owner name:nil];
            [battle recordAttackType:(int)(owner % 4 + 1) damage:17000 owner:owner];
        }
        [battle endTurn];
    }
    NSMutableDictionary *series = [battle.series mutableCopy]; series[@"action_value"] = @(battle.actionValue);
    UIView *root = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 1100, 650)]; root.backgroundColor = [UIColor colorWithRed:0.1 green:0.12 blue:0.15 alpha:1];
    NSArray *kinds = @[@"characters", @"types", @"graph", @"distribution"];
    NSArray *titles = @[@"Character Damage    DMG / DPAV", @"Damage Type Breakdown", @"Real-Time Damage    Turn / AV", @"Damage Distribution"];
    for (unsigned i = 0; i < 4; i++) {
        VeritasPanel *panel = [[VeritasPanel alloc] initWithTitle:titles[i] identifier:@"preview"];
        panel.frame = CGRectMake(20 + (i % 2) * 540, 20 + (i / 2) * 315, 520, 295);
        panel.backgroundColor = [UIColor colorWithWhite:0.055 alpha:0.8]; panel.layer.borderWidth = 0.5;
        panel.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.4].CGColor;
        panel.title.textColor = UIColor.whiteColor; panel.title.font = [UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
        VeritasDamageCharts *chart = [VeritasDamageCharts new]; chart.kind = kinds[i]; chart.textColor = UIColor.whiteColor;
        chart.textSize = 13; chart.pie = YES; chart.showLegend = YES; chart.series = series; chart.backgroundColor = UIColor.clearColor; chart.opaque = NO;
        [panel.stack addArrangedSubview:chart]; [chart.heightAnchor constraintEqualToConstant:240].active = YES;
        [root addSubview:panel];
    }
    [root layoutIfNeeded];
    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:root.bounds.size];
    NSData *png = [renderer PNGDataWithActions:^(UIGraphicsImageRendererContext *context) { [root.layer renderInContext:context.CGContext]; }];
    return [png writeToFile:@"build/plugins/VeritasPreview.png" atomically:YES] ? 0 : 1;
} }
