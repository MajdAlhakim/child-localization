import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:file_picker/file_picker.dart';

const String _baseUrl = 'https://trakn.duckdns.org';
const String _apiKey  = '580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990';

// Floor plan coordinate constants (match Android app)
const double _fpW    = 595.0;
const double _fpH    = 842.0;
const double _pxPerM = 10.0;

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

class SetupScreen extends StatefulWidget {
  const SetupScreen({super.key});

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  List<Map<String, dynamic>> _aps = [];
  bool   _loadingAps = false;
  String? _uploadStatus;
  bool   _uploading = false;
  String? _floorPlanUrl;
  bool   _floorPlanLoaded = false;
  // Hovered AP bssid for highlight
  String? _hoveredBssid;

  @override
  void initState() {
    super.initState();
    _fetchAps();
    _floorPlanUrl = '$_baseUrl/api/v1/venue/floor-plan';
  }

  // ── API calls ───────────────────────────────────────────────────────────────

  Future<void> _fetchAps() async {
    setState(() => _loadingAps = true);
    try {
      final resp = await http.get(
        Uri.parse('$_baseUrl/api/v1/venue/aps'),
        headers: {'X-API-Key': _apiKey},
      );
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        setState(() {
          _aps = List<Map<String, dynamic>>.from(data['access_points'] ?? []);
        });
      }
    } catch (_) {}
    setState(() => _loadingAps = false);
  }

  Future<void> _deleteAp(String bssid) async {
    final encoded = Uri.encodeComponent(bssid);
    await http.delete(
      Uri.parse('$_baseUrl/api/v1/venue/ap/$encoded'),
      headers: {'X-API-Key': _apiKey},
    );
    await _fetchAps();
  }

  Future<void> _deleteAllAps() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: const Color(0xFF1c2128),
        title: const Text('Clear all APs?', style: TextStyle(color: Colors.white)),
        content: const Text(
          'This will delete all placed APs from the backend.',
          style: TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete all', style: TextStyle(color: Colors.redAccent)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await http.delete(
      Uri.parse('$_baseUrl/api/v1/venue/aps'),
      headers: {'X-API-Key': _apiKey},
    );
    await _fetchAps();
  }

  Future<void> _uploadFloorPlan() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['png', 'jpg', 'jpeg', 'svg'],
      withData: true,
    );
    if (result == null || result.files.single.bytes == null) return;

    final file  = result.files.single;
    final bytes = file.bytes!;
    final ext   = (file.extension ?? 'png').toLowerCase();
    final mime  = switch (ext) {
      'svg' => 'image/svg+xml',
      'png' => 'image/png',
      _     => 'image/jpeg',
    };

    setState(() { _uploading = true; _uploadStatus = null; });
    try {
      final req = http.MultipartRequest(
        'POST',
        Uri.parse('$_baseUrl/api/v1/venue/floor-plan'),
      )
        ..headers['X-API-Key'] = _apiKey
        ..files.add(http.MultipartFile.fromBytes(
          'file', bytes,
          filename: file.name,
          contentType: MediaType.parse(mime),
        ));

      final resp = await req.send();
      if (resp.statusCode == 200) {
        setState(() {
          _uploadStatus     = '✓ Floor plan uploaded';
          _floorPlanLoaded  = false;
          _floorPlanUrl     =
              '$_baseUrl/api/v1/venue/floor-plan?t=${DateTime.now().millisecondsSinceEpoch}';
        });
      } else {
        setState(() => _uploadStatus = '✗ Upload failed (${resp.statusCode})');
      }
    } catch (e) {
      setState(() => _uploadStatus = '✗ $e');
    }
    setState(() => _uploading = false);
  }

  // ── Build ────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0d1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161b22),
        foregroundColor: Colors.white,
        title: const Text(
          'AP Setup & Floor Plan',
          style: TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.bold),
        ),
        actions: [
          IconButton(
            onPressed: _fetchAps,
            icon: const Icon(Icons.refresh, color: Colors.white70),
            tooltip: 'Refresh APs',
          ),
        ],
      ),
      body: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Left: floor plan ──────────────────────────────────────────────
          Expanded(
            flex: 3,
            child: Column(
              children: [
                _SectionHeader(
                  title: 'Floor Plan',
                  action: Row(children: [
                    if (_uploadStatus != null)
                      Padding(
                        padding: const EdgeInsets.only(right: 10),
                        child: Text(
                          _uploadStatus!,
                          style: TextStyle(
                            color: _uploadStatus!.startsWith('✓')
                                ? Colors.greenAccent
                                : Colors.redAccent,
                            fontSize: 12,
                            fontFamily: 'monospace',
                          ),
                        ),
                      ),
                    ElevatedButton.icon(
                      onPressed: _uploading ? null : _uploadFloorPlan,
                      icon: _uploading
                          ? const SizedBox(
                              width: 14, height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                          : const Icon(Icons.upload_file, size: 16),
                      label: const Text('Upload PNG / JPEG / SVG'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF238636),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      ),
                    ),
                  ]),
                ),
                Expanded(child: _buildFloorPlanPanel()),
              ],
            ),
          ),

          // ── Right: AP list ─────────────────────────────────────────────────
          SizedBox(
            width: 360,
            child: Column(
              children: [
                _SectionHeader(
                  title: 'Placed APs (${_aps.length})',
                  action: Row(children: [
                    IconButton(
                      onPressed: _fetchAps,
                      icon: const Icon(Icons.refresh, color: Colors.white70, size: 18),
                      tooltip: 'Refresh',
                    ),
                    if (_aps.isNotEmpty)
                      IconButton(
                        onPressed: _deleteAllAps,
                        icon: const Icon(Icons.delete_sweep, color: Colors.redAccent, size: 18),
                        tooltip: 'Clear all APs',
                      ),
                  ]),
                ),
                Expanded(child: _buildApList()),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Floor plan panel ────────────────────────────────────────────────────────

  Widget _buildFloorPlanPanel() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: _floorPlanUrl == null
          ? const Center(
              child: Text('No floor plan yet', style: TextStyle(color: Colors.grey)))
          : LayoutBuilder(builder: (context, constraints) {
              final canvasSize = Size(constraints.maxWidth, constraints.maxHeight);
              return Stack(children: [
                // Floor plan image
                Positioned.fill(
                  child: Image.network(
                    _floorPlanUrl!,
                    fit: BoxFit.contain,
                    loadingBuilder: (_, child, progress) {
                      if (progress == null) {
                        if (!_floorPlanLoaded) {
                          WidgetsBinding.instance.addPostFrameCallback(
                            (_) { if (mounted) setState(() => _floorPlanLoaded = true); },
                          );
                        }
                        return child;
                      }
                      return const Center(child: CircularProgressIndicator());
                    },
                    errorBuilder: (_, _, _) => const Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.map_outlined, color: Colors.grey, size: 48),
                          SizedBox(height: 12),
                          Text('No floor plan uploaded yet',
                              style: TextStyle(color: Colors.grey)),
                          Text('Use the button above to upload a PNG, JPEG, or SVG.',
                              style: TextStyle(color: Colors.grey, fontSize: 12)),
                        ],
                      ),
                    ),
                  ),
                ),

                // AP markers overlay
                if (_floorPlanLoaded && _aps.isNotEmpty)
                  Positioned.fill(
                    child: CustomPaint(
                      painter: _ApMarkerPainter(
                        aps:          _aps,
                        canvasSize:   canvasSize,
                        hoveredBssid: _hoveredBssid,
                      ),
                    ),
                  ),
              ]);
            }),
    );
  }

  // ── AP list ─────────────────────────────────────────────────────────────────

  Widget _buildApList() {
    if (_loadingAps) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_aps.isEmpty) {
      return const Center(
        child: Text(
          'No APs placed yet.\n\nWalk around with the Android app\nand tap your location on the map.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey, fontSize: 13),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(12),
      itemCount: _aps.length,
      separatorBuilder: (_, _) => const SizedBox(height: 6),
      itemBuilder: (_, i) => _ApTile(
        ap:            _aps[i],
        hovered:       _aps[i]['bssid'] == _hoveredBssid,
        onHover:       (v) => setState(() =>
            _hoveredBssid = v ? _aps[i]['bssid'] as String : null),
        onDelete:      () => _deleteAp(_aps[i]['bssid'] as String),
      ),
    );
  }
}

// ── AP marker painter ─────────────────────────────────────────────────────────

class _ApMarkerPainter extends CustomPainter {
  final List<Map<String, dynamic>> aps;
  final Size   canvasSize;
  final String? hoveredBssid;

  const _ApMarkerPainter({
    required this.aps,
    required this.canvasSize,
    required this.hoveredBssid,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final fp = _containRect(size);
    final sx = fp.width  / _fpW;
    final sy = fp.height / _fpH;

    for (final ap in aps) {
      final xm = (ap['x'] as num?)?.toDouble() ?? 0;
      final ym = (ap['y'] as num?)?.toDouble() ?? 0;
      final px = fp.left + xm * _pxPerM * sx;
      final py = fp.top  + ym * _pxPerM * sy;
      final c  = Offset(px, py);

      final hovered = ap['bssid'] == hoveredBssid;
      final color   = hovered ? Colors.green : Colors.orange;

      // Pulse rings
      for (final r in [22.0, 16.0]) {
        canvas.drawCircle(c, r, Paint()..color = color.withValues(alpha: 0.08));
      }
      canvas.drawCircle(c, 14, Paint()..color = color.withValues(alpha: 0.3)
          ..style = PaintingStyle.stroke..strokeWidth = 1.5);
      canvas.drawCircle(c, 8, Paint()..color = color);
      canvas.drawCircle(c, 3, Paint()..color = Colors.white.withValues(alpha: 0.6));

      // Label
      final ssid = (ap['ssid'] as String?) ?? '';
      final label = ssid.isEmpty ? ap['bssid'] as String : ssid;
      final tp = TextPainter(
        text: TextSpan(
          text: label,
          style: TextStyle(
            color: color,
            fontSize: 10,
            fontWeight: FontWeight.bold,
            shadows: const [Shadow(color: Colors.black, blurRadius: 4)],
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(px - tp.width / 2, py + 11));
    }
  }

  @override
  bool shouldRepaint(_ApMarkerPainter old) =>
      old.aps != aps || old.hoveredBssid != hoveredBssid || old.canvasSize != canvasSize;
}

// ── AP tile ───────────────────────────────────────────────────────────────────

class _ApTile extends StatelessWidget {
  final Map<String, dynamic> ap;
  final bool     hovered;
  final ValueChanged<bool> onHover;
  final VoidCallback onDelete;

  const _ApTile({
    required this.ap,
    required this.hovered,
    required this.onHover,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final ssid    = ap['ssid']     as String? ?? '';
    final bssid   = ap['bssid']   as String? ?? '';
    final rssiRef = (ap['rssi_ref'] as num?)?.toDouble() ?? 0.0;
    final x       = (ap['x'] as num?)?.toDouble() ?? 0.0;
    final y       = (ap['y'] as num?)?.toDouble() ?? 0.0;

    return MouseRegion(
      onEnter: (_) => onHover(true),
      onExit:  (_) => onHover(false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: hovered ? const Color(0xFF22301c) : const Color(0xFF1c2128),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: hovered ? Colors.green.withValues(alpha: 0.6) : const Color(0xFF30363d),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Icon(Icons.wifi, size: 14,
                        color: hovered ? Colors.green : const Color(0xFF58a6ff)),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        ssid.isEmpty ? '<Hidden>' : ssid,
                        style: TextStyle(
                          color: hovered ? Colors.green : Colors.white,
                          fontWeight: FontWeight.w600,
                          fontSize: 13,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ]),
                  const SizedBox(height: 3),
                  Text(bssid,
                      style: const TextStyle(
                          color: Colors.white54, fontSize: 11, fontFamily: 'monospace')),
                  const SizedBox(height: 6),
                  Row(children: [
                    _Chip('${rssiRef.toInt()} dBm', Colors.orange),
                    const SizedBox(width: 6),
                    _Chip('(${x.toStringAsFixed(1)}, ${y.toStringAsFixed(1)}) m', Colors.blue),
                  ]),
                ],
              ),
            ),
            // Delete button
            IconButton(
              onPressed: () async {
                final ok = await showDialog<bool>(
                  context: context,
                  builder: (_) => AlertDialog(
                    backgroundColor: const Color(0xFF1c2128),
                    title: const Text('Delete AP?',
                        style: TextStyle(color: Colors.white)),
                    content: Text(
                      'Remove ${ssid.isEmpty ? bssid : ssid} from the map?',
                      style: const TextStyle(color: Colors.white70),
                    ),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: const Text('Cancel'),
                      ),
                      TextButton(
                        onPressed: () => Navigator.pop(context, true),
                        child: const Text('Delete',
                            style: TextStyle(color: Colors.redAccent)),
                      ),
                    ],
                  ),
                );
                if (ok == true) onDelete();
              },
              icon: const Icon(Icons.delete_outline, color: Colors.redAccent, size: 18),
              tooltip: 'Delete AP',
            ),
          ],
        ),
      ),
    );
  }
}

// ── Shared widgets ────────────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  final String title;
  final Widget action;
  const _SectionHeader({required this.title, required this.action});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF161b22),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(children: [
        Text(title,
            style: const TextStyle(
                color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14)),
        const Spacer(),
        action,
      ]),
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final Color  color;
  const _Chip(this.label, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(label,
          style: TextStyle(
              color: color,
              fontSize: 10,
              fontFamily: 'monospace',
              fontWeight: FontWeight.w600)),
    );
  }
}
