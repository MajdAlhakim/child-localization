// app/lib/services/auth_service.dart
// JWT authentication service — TASK-16

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class AuthService {
  static const String _tokenKey = 'jwt_token';
  static const String _baseUrl = 'https://trakn.duckdns.org';

  Future<String> login(String email, String password) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/api/v1/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (response.statusCode == 200) {
      final token =
          (jsonDecode(response.body) as Map<String, dynamic>)['access_token']
              as String;
      await _saveToken(token);
      return token;
    } else if (response.statusCode == 401) {
      throw Exception('Invalid email or password.');
    } else {
      throw Exception('Login failed: HTTP ${response.statusCode}');
    }
  }

  Future<String> register(String email, String password) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/api/v1/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (response.statusCode == 201) {
      final token =
          (jsonDecode(response.body) as Map<String, dynamic>)['access_token']
              as String;
      await _saveToken(token);
      return token;
    } else if (response.statusCode == 409) {
      throw Exception('Email is already registered. Please sign in.');
    } else {
      throw Exception('Registration failed: HTTP ${response.statusCode}');
    }
  }

  Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  Future<bool> isLoggedIn() async => (await getToken()) != null;

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  Future<void> _saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }
}
