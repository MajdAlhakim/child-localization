class PositionUpdate {
  final String tagId;
  final double x;
  final double y;
  final double heading;
  final double headingDeg;
  final int stepCount;
  final double confidence;
  final String source;
  final String mode;
  final bool biasCalibrated;
  final String ts;

  PositionUpdate({
    required this.tagId,
    required this.x,
    required this.y,
    required this.heading,
    required this.headingDeg,
    required this.stepCount,
    required this.confidence,
    required this.source,
    required this.mode,
    required this.biasCalibrated,
    required this.ts,
  });

  factory PositionUpdate.fromJson(Map<String, dynamic> json) {
    return PositionUpdate(
      tagId:          json['tag_id']          as String,
      x:              (json['x']              as num).toDouble(),
      y:              (json['y']              as num).toDouble(),
      heading:        (json['heading']        as num).toDouble(),
      headingDeg:     (json['heading_deg']    as num).toDouble(),
      stepCount:      json['step_count']      as int,
      confidence:     (json['confidence']     as num).toDouble(),
      source:         json['source']          as String,
      mode:           json['mode']            as String,
      biasCalibrated: json['bias_calibrated'] as bool,
      ts:             json['ts']              as String,
    );
  }
}
