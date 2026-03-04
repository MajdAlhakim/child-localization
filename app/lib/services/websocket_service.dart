// app/lib/services/websocket_service.dart
// WebSocket service with auto-reconnect — TASK-16
// Connects to: wss://trakn.duckdns.org/ws/position/DEVICE_ID

import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/position_update.dart';

enum WsConnectionState { connecting, connected, disconnected, reconnecting }

class WebSocketService {
  static const String _host = 'wss://trakn.duckdns.org';

  final String deviceId;

  WebSocketService(this.deviceId);

  WebSocketChannel? _channel;
  StreamController<PositionUpdate>? _controller;

  WsConnectionState _state = WsConnectionState.disconnected;
  WsConnectionState get connectionState => _state;

  Stream<PositionUpdate> connect() {
    _controller ??= StreamController<PositionUpdate>.broadcast();
    if (_state == WsConnectionState.disconnected) {
      _connect(delay: Duration.zero);
    }
    return _controller!.stream;
  }

  void _connect({required Duration delay}) {
    _state = delay == Duration.zero
        ? WsConnectionState.connecting
        : WsConnectionState.reconnecting;

    Future.delayed(delay, () async {
      if (_controller?.isClosed ?? true) return;

      try {
        final uri = Uri.parse('$_host/ws/position/$deviceId');
        _channel = IOWebSocketChannel.connect(uri);
        _state = WsConnectionState.connected;
        _onConnected();

        _channel!.stream.listen(
          (dynamic data) {
            try {
              final json = jsonDecode(data as String) as Map<String, dynamic>;
              _controller?.add(PositionUpdate.fromJson(json));
            } catch (_) {
              // Malformed frame — ignore
            }
          },
          onDone: () => _handleDisconnect(),
          onError: (_) => _handleDisconnect(),
          cancelOnError: true,
        );
      } catch (_) {
        _handleDisconnect();
      }
    });
  }

  Duration _backoff = const Duration(seconds: 1);
  static const Duration _maxBackoff = Duration(seconds: 30);

  void _handleDisconnect() {
    _state = WsConnectionState.reconnecting;
    final next = _backoff;
    _backoff = _backoff * 2 > _maxBackoff ? _maxBackoff : _backoff * 2;
    _connect(delay: next);
  }

  void _onConnected() {
    _backoff = const Duration(seconds: 1);
  }

  void dispose() {
    _state = WsConnectionState.disconnected;
    _channel?.sink.close();
    _controller?.close();
    _controller = null;
  }
}
