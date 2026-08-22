import objc
from AppKit import (
    NSAnimationContext,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSEvent,
    NSRectFill,
    NSScreen,
    NSView,
    NSWindow,
    NSWindowStyleMaskBorderless,
)
from Foundation import NSAttributedString


THORN_COUNT = 32


class _ThornView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_ThornView, self).initWithFrame_(frame)
        if self:
            self.amplitudes = [0.0] * THORN_COUNT
            self._smoothed = 0.0
            self.elapsed_text = ""
        return self

    def _thorn_path_at(self, cx, baseline, half_w, height, lean):
        path = NSBezierPath.alloc().init()

        path.moveToPoint_((cx - half_w * 0.7, baseline))

        path.curveToPoint_controlPoint1_controlPoint2_(
            (cx + lean * 0.3, baseline + height),
            (cx - half_w * 1.5, baseline + height * 0.3),
            (cx - half_w * 0.4, baseline + height * 0.6),
        )

        path.lineToPoint_((cx + lean * 0.3, baseline + height * 0.98))

        path.curveToPoint_controlPoint1_controlPoint2_(
            (cx + half_w * 0.7, baseline),
            (cx + half_w * 0.4, baseline + height * 0.6),
            (cx + half_w * 1.5, baseline + height * 0.3),
        )

        path.closePath()
        return path

    def drawRect_(self, rect):
        NSColor.clearColor().set()
        NSRectFill(self.bounds())

        w = self.bounds().size.width
        h = self.bounds().size.height
        seg = w / THORN_COUNT
        baseline = h * 0.6

        for i, amp in enumerate(self.amplitudes):
            cx = i * seg + seg / 2
            peak = amp * h * 0.55
            if peak < 0.5:
                continue

            lean = seg * 0.25 * (1 if i % 2 == 0 else -1)

            glow_path = self._thorn_path_at(cx, baseline, seg * 0.7, peak * 1.6, lean)
            glow_alpha = 0.04 * amp
            if glow_alpha > 0.01:
                NSColor.colorWithCalibratedWhite_alpha_(1.0, glow_alpha).set()
                glow_path.fill()

            thorn_path = self._thorn_path_at(cx, baseline, seg * 0.45, peak, lean)
            alpha = 0.15 + 0.85 * amp
            NSColor.colorWithCalibratedWhite_alpha_(1.0, alpha).set()
            thorn_path.fill()

        vine = NSBezierPath.alloc().init()
        vine.moveToPoint_((0, baseline))
        for i in range(THORN_COUNT):
            cx = i * seg + seg / 2
            vine.curveToPoint_controlPoint1_controlPoint2_(
                (cx + seg / 2, baseline),
                (cx + seg * 0.25, baseline + self.amplitudes[i] * h * 0.04),
                (cx + seg * 0.25, baseline + self.amplitudes[i] * h * 0.04),
            )
        vine.lineToPoint_((w, baseline))
        vine.setLineWidth_(1.2)
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.25).set()
        vine.stroke()

        vine_glow = vine.copy()
        vine_glow.setLineWidth_(4)
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.05).set()
        vine_glow.stroke()

        if self.elapsed_text:
            attrs = {
                "NSFont": NSFont.monospacedDigitSystemFontOfSize_weight_(11.0, 0.5),
                "NSColor": NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.8),
            }
            text = NSAttributedString.alloc().initWithString_attributes_(
                self.elapsed_text, attrs
            )
            size = text.size()
            text.drawAtPoint_((w - size.width - 10, baseline + 4))


class WaveformOverlay:
    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._view = None
        self._window = None
        self._hiding = False

    def show(self):
        if self._window or self._hiding:
            return
        screen = self._screen_under_mouse() or NSScreen.mainScreen().frame()
        if screen is None:
            return

        w = self._config.get("waveform_width", 280)
        h = self._config.get("waveform_height", 36)
        y_pos = self._config.get("waveform_y", "bottom")

        if y_pos == "bottom":
            y = 48
        elif y_pos == "top":
            y = screen.size.height - h - 48
        else:
            y = int(y_pos)

        x = (screen.size.width - w) / 2

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, y), (w, h)),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setLevel_(1000)
        self._window.setIgnoresMouseEvents_(True)

        self._view = _ThornView.alloc().initWithFrame_(((0, 0), (w, h)))
        self._window.setContentView_(self._view)

        self._window.setAlphaValue_(0)
        self._window.orderFrontRegardless()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.15)
        self._window.animator().setAlphaValue_(1)
        NSAnimationContext.endGrouping()

    @staticmethod
    def _screen_under_mouse():
        """多显示器下跟随鼠标所在屏幕；失败回退主屏。"""
        try:
            mouse = NSEvent.mouseLocation()
            for scr in NSScreen.screens():
                f = scr.frame()
                if (
                    f.origin.x <= mouse.x <= f.origin.x + f.size.width
                    and f.origin.y <= mouse.y <= f.origin.y + f.size.height
                ):
                    return f
        except Exception:
            pass
        return None

    def update(self, amplitude: float, elapsed_text: str = ""):
        if self._view:
            self._view._smoothed = (
                self._view._smoothed * 0.6 + min(amplitude, 1.0) * 0.4
            )
            self._view.amplitudes = self._view.amplitudes[1:] + [
                self._view._smoothed
            ]
            self._view.elapsed_text = elapsed_text
            self._view.setNeedsDisplay_(True)

    def hide(self):
        if not self._window:
            return
        self._hiding = True
        win = self._window
        self._window = None
        self._view = None

        def on_finish():
            win.orderOut_(None)
            self._hiding = False

        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.2)
        NSAnimationContext.currentContext().setCompletionHandler_(on_finish)
        win.animator().setAlphaValue_(0)
        NSAnimationContext.endGrouping()
