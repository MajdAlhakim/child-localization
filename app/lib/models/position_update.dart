// app/lib/models/position_update.dart
// Dart model matching the locked WebSocket wire format (workspace rules section 8).

class PositionUpdate {
  final String deviceId;
  final DateTime tsUtc;
  final double xM;
  final double yM;
  final String source;
  final double confidence;
  final int activeAps;
  final String mode;

  const PositionUpdate({
    required this.deviceId,
    required this.tsUtc,
    required this.xM,
    required this.yM,
    required this.source,
    required this.confidence,
    required this.activeAps,
    required this.mode,
  });

  factory PositionUpdate.fromJson(Map<String, dynamic> json) {
    return PositionUpdate(
      deviceId: json['device_id'] as String,
      tsUtc: DateTime.parse(json['ts_utc'] as String),
      xM: (json['x_m'] as num).toDouble(),
      yM: (json['y_m'] as num).toDouble(),
      source: json['source'] as String,
      confidence: (json['confidence'] as num).toDouble(),
      activeAps: json['active_aps'] as int,
      mode: json['mode'] as String,
    );
  }

  Map<String, dynamic> toJson() => {
    'device_id': deviceId,
    'ts_utc': tsUtc.toIso8601String(),
    'x_m': xM,
    'y_m': yM,
    'source': source,
    'confidence': confidence,
    'active_aps': activeAps,
    'mode': mode,
  };

  @override
  String toString() =>
      'PositionUpdate(device=$deviceId, x=${xM.toStringAsFixed(2)}, '
      'y=${yM.toStringAsFixed(2)}, mode=$mode)';
}
