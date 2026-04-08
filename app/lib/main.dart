import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'screens/home_screen.dart';
import 'services/websocket_service.dart';

void main() {
  runApp(
    ChangeNotifierProvider(
      create: (_) => WebSocketService(),
      child: const TRAKNApp(),
    ),
  );
}

class TRAKNApp extends StatelessWidget {
  const TRAKNApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TRAKN',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
