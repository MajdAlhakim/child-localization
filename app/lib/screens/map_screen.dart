import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/position_update.dart';
import '../services/websocket_service.dart';

// ── Floor plan coordinate constants (must match Android app) ─────────────────
const double _fpW    = 595.0;  // floor plan native px width
const double _fpH    = 842.0;  // floor plan native px height
const double _pxPerM = 10.0;   // pixels per metre
const String _fpUrl  = 'https://trakn.duckdns.org/api/v1/venue/floor-plan';

// Map (xm, ym) to canvas coordinates given the rendered rect of the image.
Offset _mToScreen(double xm, double ym, Rect fp) {
  return Offset(
    fp.left + xm * _pxPerM * (fp.width / _fpW),
    fp.top  + ym * _pxPerM * (fp.height / _fpH),
  );
}

// BoxFit.contain rect for the floor plan inside a canvas.
Rect _containRect(Size canvas) {
  final imgAspect    = _fpW / _fpH;
  final canvasAspect = canvas.width / canvas.height;
  double w, h;
  if (canvasAspect > imgAspect) {
    h = canvas.height; w = h * imgAspect;
  } else {
    w = canvas.width; h = w / imgAspect;
  }
  return Rect.fromLTWH((canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
}

// ── Screen ────────────────────────────────────────────────────────────────────

class MapScreen extends StatefulWidget {
  final String tagId;
  const MapScreen({super.key, required this.tagId});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

enum _FpStatus { loading, ok, failed }

class _MapScreenState extends State<MapScreen> {
  late final WebSocketService _svc;
  _FpStatus _fpStatus = _FpStatus.loading;

  @override
  void initState() {
    super.initState();
    _svc = context.read<WebSocketService>();
    _svc.startTracking(widget.tagId);
  }

  @override
  void dispose() {
    _svc.stopTracking();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final svc       = context.watch<WebSocketService>();
    final pos       = svc.lastPosition;
    final connState = svc.connectionState;

    return Scaffold(
      backgroundColor: const Color(0xFF0d1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161b22),
        foregroundColor: Colors.white,
        title: Text(
          'TRAKN — ${widget.tagId}',
          style: const TextStyle(fontSize: 14, fontFamily: 'monospace'),
        ),
        actions: [
          _StatusChip(label: _connLabel(connState), color: _connColor(connState)),
          if (pos != null) ...[
            const SizedBox(width: 6),
            _StatusChip(label: _modeLabel(pos.mode), color: _modeColor(pos.mode)),
            const SizedBox(width: 6),
            _StatusChip(
              label: pos.biasCalibrated ? 'Ready' : 'Calibrating',
              color: pos.biasCalibrated ? Colors.green : Colors.grey,
            ),
          ],
          const SizedBox(width: 12),
        ],
      ),
      body: Column(
        children: [
          // Signal-lost banner
          if (connState == 'disconnected' && pos != null)
            Container(
              color: const Color(0xFF6e1a1a),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: const Row(children: [
                Icon(Icons.signal_wifi_off, color: Colors.white, size: 14),
                SizedBox(width: 8),
                Text('Signal lost — last known position shown',
                    style: TextStyle(color: Colors.white, fontSize: 12)),
              ]),
            ),

          // Map area
          Expanded(child: _buildMapArea(pos, connState)),

          // Info panel
          _InfoPanel(pos: pos),
        ],
      ),
    );
  }

  Widget _buildMapArea(PositionUpdate? pos, String connState) {
    if (connState == 'disconnected' && pos == null) {
      return const Center(
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(Icons.location_off, size: 48, color: Colors.grey),
          SizedBox(height: 16),
          Text('Waiting for device...', style: TextStyle(color: Colors.grey, fontSize: 18)),
        ]),
      );
    }

    return LayoutBuilder(builder: (context, constraints) {
      final canvasSize = Size(constraints.maxWidth, constraints.maxHeight);
      final fp = _containRect(canvasSize);

      return InteractiveViewer(
        minScale: 0.5,
        maxScale: 10.0,
        child: SizedBox.fromSize(
          size: canvasSize,
          child: Stack(children: [
            // Background — floor plan or grid fallback
            if (_fpStatus != _FpStatus.failed)
              Positioned.fill(
                child: Image.network(
                  _fpUrl,
                  fit: BoxFit.contain,
                  loadingBuilder: (_, child, progress) {
                    if (progress == null) {
                      if (_fpStatus != _FpStatus.ok) {
                        WidgetsBinding.instance.addPostFrameCallback(
                          (_) { if (mounted) setState(() => _fpStatus = _FpStatus.ok); },
                        );
                      }
                      return child;
                    }
                    return Center(
                      child: CircularProgressIndicator(
                        value: progress.expectedTotalBytes != null
                            ? progress.cumulativeBytesLoaded / progress.expectedTotalBytes!
                            : null,
                        color: Colors.blue,
                      ),
                    );
                  },
                  errorBuilder: (_, _, _) {
                    WidgetsBinding.instance.addPostFrameCallback(
                      (_) { if (mounted) setState(() => _fpStatus = _FpStatus.failed); },
                    );
                    return const SizedBox.shrink();
                  },
                ),
              ),

            if (_fpStatus == _FpStatus.failed)
              Positioned.fill(
                child: CustomPaint(
                  painter: _GridPainter(
                    position: pos != null ? Offset(pos.x, pos.y) : null,
                    heading:  pos?.heading ?? 0.0,
                  ),
                ),
              ),

            // Position marker overlay (floor plan mode)
            if (pos != null && _fpStatus == _FpStatus.ok)
              Positioned.fill(
                child: CustomPaint(
                  painter: _MarkerPainter(
                    screen: _mToScreen(pos.x, pos.y, fp),
                    heading: pos.heading,
                  ),
                ),
              ),

            // No floor plan hint
            if (_fpStatus == _FpStatus.failed)
              Positioned(
                top: 8, left: 0, right: 0,
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.orange.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: Colors.orange.withValues(alpha: 0.4)),
                    ),
                    child: const Text(
                      'No floor plan — upload one in AP Setup',
                      style: TextStyle(color: Colors.orange, fontSize: 11),
                    ),
                  ),
                ),
              ),
          ]),
        ),
      );
    });
  }
}

// ── Painters ──────────────────────────────────────────────────────────────────

class _MarkerPainter extends CustomPainter {
  final Offset screen;
  final double heading;
  const _MarkerPainter({required this.screen, required this.heading});

  @override
  void paint(Canvas canvas, Size size) {
    // Pulse rings
    for (final r in [24.0, 18.0, 12.0]) {
      canvas.drawCircle(screen, r,
          Paint()..color = Colors.blue.withValues(alpha: 0.08 + (24 - r) * 0.005));
    }
    // Arrow
    final arrowEnd = Offset(
      screen.dx + 22 * math.cos(heading),
      screen.dy - 22 * math.sin(heading),
    );
    canvas.drawLine(screen, arrowEnd,
        Paint()
          ..color = Colors.amber
          ..strokeWidth = 2.5
          ..strokeCap = StrokeCap.round);
    // Dot
    canvas.drawCircle(screen, 10, Paint()..color = Colors.blue.shade400);
    canvas.drawCircle(screen, 10,
        Paint()
          ..color = Colors.white
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2);
    canvas.drawCircle(screen, 4, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(_MarkerPainter old) =>
      old.screen != screen || old.heading != heading;
}

class _GridPainter extends CustomPainter {
  static const double _ppm    = 20.0;
  static const int    _radius = 10;

  final Offset? position;
  final double  heading;
  const _GridPainter({required this.position, required this.heading});

  Offset _w2s(Offset world, Size size) =>
      Offset(size.width / 2 + world.dx * _ppm, size.height / 2 - world.dy * _ppm);

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final minor = Paint()..color = const Color(0xFF21262d)..strokeWidth = 0.5;
    final axis  = Paint()..color = const Color(0xFF444c56)..strokeWidth = 1.0;

    for (int i = -_radius; i <= _radius; i++) {
      final sx = cx + i * _ppm;
      final sy = cy + i * _ppm;
      final p  = i == 0 ? axis : minor;
      canvas.drawLine(Offset(sx, 0), Offset(sx, size.height), p);
      canvas.drawLine(Offset(0, sy), Offset(size.width, sy), p);
    }

    final labelStyle = TextStyle(color: Colors.grey.shade600, fontSize: 9);
    for (int i = -_radius; i <= _radius; i += 2) {
      if (i == 0) continue;
      _label(canvas, '$i', Offset(cx + i * _ppm, cy + 10), labelStyle);
      _label(canvas, '$i', Offset(cx - 16, cy - i * _ppm), labelStyle);
    }

    // Origin cross
    final originPaint = Paint()..color = const Color(0xFF58a6ff)..strokeWidth = 1.5;
    canvas.drawLine(Offset(cx - 7, cy), Offset(cx + 7, cy), originPaint);
    canvas.drawLine(Offset(cx, cy - 7), Offset(cx, cy + 7), originPaint);

    if (position == null) return;
    final sp = _w2s(position!, size);
    // Arrow
    final arrowEnd = Offset(sp.dx + 22 * math.cos(heading), sp.dy - 22 * math.sin(heading));
    canvas.drawLine(sp, arrowEnd,
        Paint()..color = Colors.amber..strokeWidth = 2.5..strokeCap = StrokeCap.round);
    // Dot
    canvas.drawCircle(sp, 12, Paint()..color = Colors.blue.shade400);
    canvas.drawCircle(sp, 12,
        Paint()..color = Colors.white..style = PaintingStyle.stroke..strokeWidth = 2);
  }

  void _label(Canvas canvas, String text, Offset center, TextStyle style) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(_GridPainter old) =>
      old.position != position || old.heading != heading;
}

// ── Status helpers ────────────────────────────────────────────────────────────

String _connLabel(String s) => switch (s) {
  'connected'  => 'Connected',
  'connecting' => 'Connecting…',
  _            => 'Disconnected',
};
Color _connColor(String s) => switch (s) {
  'connected'  => Colors.green,
  'connecting' => Colors.grey,
  _            => Colors.red,
};
String _modeLabel(String m) => switch (m) {
  'normal'       => 'Normal',
  'disconnected' => 'Disconnected',
  _              => 'IMU Only',
};
Color _modeColor(String m) => switch (m) {
  'normal'       => Colors.green,
  'disconnected' => Colors.red,
  _              => Colors.orange,
};

// ── Widgets ───────────────────────────────────────────────────────────────────

class _StatusChip extends StatelessWidget {
  final String label;
  final Color  color;
  const _StatusChip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 6, height: 6,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(label, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.bold)),
      ]),
    );
  }
}

class _InfoPanel extends StatelessWidget {
  final PositionUpdate? pos;
  const _InfoPanel({required this.pos});

  @override
  Widget build(BuildContext context) {
    final x = pos?.x ?? 0.0;
    final y = pos?.y ?? 0.0;
    return Container(
      color: const Color(0xFF161b22),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _InfoItem('Steps',    '${pos?.stepCount ?? 0}'),
          _InfoItem('Position', '(${x.toStringAsFixed(2)}, ${y.toStringAsFixed(2)}) m'),
          _InfoItem('Heading',  '${(pos?.headingDeg ?? 0.0).toStringAsFixed(0)}°'),
          _InfoItem('Source',   pos?.source ?? '—'),
          _InfoItem('Conf.',    pos != null ? '${(pos!.confidence * 100).toStringAsFixed(0)}%' : '—'),
        ],
      ),
    );
  }
}

class _InfoItem extends StatelessWidget {
  final String label;
  final String value;
  const _InfoItem(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Text(label, style: const TextStyle(color: Colors.grey, fontSize: 10)),
      const SizedBox(height: 2),
      Text(value, style: const TextStyle(
        color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold)),
    ]);
  }
}
