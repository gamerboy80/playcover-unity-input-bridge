#ifndef NATIVE_CAPTURE_H
#define NATIVE_CAPTURE_H
#include <CoreGraphics/CGGeometry.h>
#include <stdbool.h>

// AppKit uses a bottom-left origin; Quartz uses the primary display's top-left.
static inline CGPoint captureScreenPoint(CGPoint appKitPoint, double primaryTop) {
    return CGPointMake(appKitPoint.x, primaryTop-appKitPoint.y);
}

static inline bool cursorInsideContent(CGPoint point, CGRect bounds) {
    return bounds.size.width>0 && bounds.size.height>0 &&
        point.x>=CGRectGetMinX(bounds) && point.x<CGRectGetMaxX(bounds) &&
        point.y>=CGRectGetMinY(bounds) && point.y<CGRectGetMaxY(bounds);
}
#endif
