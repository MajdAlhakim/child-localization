import 'package:flutter/material.dart';
import 'map_screen.dart';
import 'setup_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  // Pre-filled for demo — user can clear and type a different ID.
  final _controller = TextEditingController(text: '24:42:E3:15:E5:72');

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Padding(
              padding: const EdgeInsets.all(32.0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.location_on, size: 64, color: Colors.blue),
                  const SizedBox(height: 16),
                  const Text(
                    'TRAKN',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 36,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 4,
                    ),
                  ),
                  const Text(
                    'Indoor Child Localization',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 14, color: Colors.grey),
                  ),
                  const SizedBox(height: 24),
                  OutlinedButton.icon(
                    onPressed: () {
                      Navigator.of(context).push(MaterialPageRoute(
                        builder: (_) => const SetupScreen(),
                      ));
                    },
                    icon: const Icon(Icons.settings_input_antenna),
                    label: const Text('AP Setup / Mapping'),
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                  ),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _controller,
                    decoration: const InputDecoration(
                      labelText: 'Tag ID',
                      hintText: 'e.g. 24:42:E3:15:E5:72',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.tag),
                    ),
                  ),
                  const SizedBox(height: 24),
                  ValueListenableBuilder<TextEditingValue>(
                    valueListenable: _controller,
                    builder: (context, value, _) {
                      return FilledButton.icon(
                        onPressed: value.text.trim().isEmpty
                            ? null
                            : () {
                                Navigator.of(context).push(MaterialPageRoute(
                                  builder: (_) =>
                                      MapScreen(tagId: value.text.trim()),
                                ));
                              },
                        icon: const Icon(Icons.play_arrow),
                        label: const Text('Start Tracking'),
                        style: FilledButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
