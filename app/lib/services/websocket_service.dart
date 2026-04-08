import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/position_update.dart';

class WebSocketService extends ChangeNotifier {
  static const String _serverHost = 'trakn.duckdns.org';
  static const Duration _reconnectDelay = Duration(seconds: 3);

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _reconnectTimer;
  Timer? _playbackTimer;
  final Queue<PositionUpdate> _queue = Queue();

  String? _tagId;
  PositionUpdate? lastPosition;
  String connectionState = 'disconnected';

  void startTracking(String tagId) {
    _tagId = tagId;
    _startPlayback();
    _connect();
  }

  void stopTracking() {
    _reconnectTimer?.cancel();
    _playbackTimer?.cancel();
    _subscription?.cancel();
    _channel?.sink.close();
    _queue.clear();
    _tagId = null;
    lastPosition = null;
    connectionState = 'disconnected';
    notifyListeners();
  }

  void _startPlayback() {
    _playbackTimer?.cancel();
    _playbackTimer = Timer.periodic(const Duration(milliseconds: 10), (_) {
      if (_queue.isNotEmpty) {
        lastPosition = _queue.removeFirst();
        notifyListeners();
      }
    });
  }

  void _connect() {
    if (_tagId == null) return;
    connectionState = 'connecting';
    notifyListeners();

    final uri = Uri.parse('wss://$_serverHost/ws/position/$_tagId');
    try {
      _channel = WebSocketChannel.connect(uri);
      _subscription = _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDone,
        cancelOnError: false,
      );
      connectionState = 'connected';
      notifyListeners();
    } catch (e) {
      debugPrint('[WS] connect error: $e');
      connectionState = 'disconnected';
      notifyListeners();
      _scheduleReconnect();
    }
  }

  void _onMessage(dynamic raw) {
    try {
      final map = jsonDecode(raw as String) as Map<String, dynamic>;
      _queue.add(PositionUpdate.fromJson(map));
    } catch (e) {
      debugPrint('[WS] parse error: $e');
    }
  }

  void _onError(dynamic error) {
    debugPrint('[WS] error: $error');
    connectionState = 'disconnected';
    notifyListeners();
    _scheduleReconnect();
  }

  void _onDone() {
    debugPrint('[WS] connection closed');
    connectionState = 'disconnected';
    notifyListeners();
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_tagId == null) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(_reconnectDelay, _connect);
  }

  @override
  void dispose() {
    stopTracking();
    super.dispose();
  }
}
