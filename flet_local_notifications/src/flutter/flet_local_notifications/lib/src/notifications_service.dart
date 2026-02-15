import 'dart:async';
import 'dart:developer' as developer;
import 'package:flet/flet.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

const String _tag = 'TrebnicNotifications';

void _log(String message) {
  final formatted = '[$_tag] $message';
  print(formatted);
  developer.log(message, name: _tag);
}

class NotificationsService extends FletService {
  NotificationsService({required super.control});

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  Completer<bool>? _initCompleter;
  DateTime? _lastShowTime;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_onMethod);
    _ensureInitialized();
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_onMethod);
    super.dispose();
  }

  Future<bool> _ensureInitialized() async {
    if (_initCompleter != null) return _initCompleter!.future;

    _initCompleter = Completer<bool>();
    _log('init() called');

    try {
      const androidSettings =
          AndroidInitializationSettings('@mipmap/ic_launcher');
      const initSettings = InitializationSettings(android: androidSettings);

      _log('_ensureInitialized: calling plugin.initialize()');
      final result = await _plugin.initialize(
        initSettings,
        onDidReceiveNotificationResponse: (response) {
          _log('onDidReceiveNotificationResponse: payload=${response.payload}');
          if (_lastShowTime != null &&
              DateTime.now().difference(_lastShowTime!).inSeconds < 3) {
            _log('ignoring duplicate tap within 3 seconds');
            return;
          }
          control.triggerEvent("notification_tap", response.payload ?? "");
        },
      );

      final initialized = result ?? false;
      _log('_ensureInitialized: plugin.initialize() returned $initialized');

      if (initialized) {
        await _createNotificationChannel();
      }

      _initCompleter!.complete(initialized);
    } catch (e, stackTrace) {
      _log('_ensureInitialized: FAILED - $e');
      _log('_ensureInitialized: stackTrace - $stackTrace');
      _initCompleter!.complete(false);
    }

    return _initCompleter!.future;
  }

  Future<void> _createNotificationChannel() async {
    _log('_createNotificationChannel: creating channel');
    try {
      final android = _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
      if (android == null) {
        _log('_createNotificationChannel: not on Android, skipping');
        return;
      }

      const channel = AndroidNotificationChannel(
        'trebnic_reminders',
        'Task reminders',
        description: 'Task reminders from Trebnic',
        importance: Importance.high,
        playSound: true,
        enableVibration: true,
      );

      await android.createNotificationChannel(channel);
      _log('_createNotificationChannel: created successfully');
    } catch (e, stackTrace) {
      _log('_createNotificationChannel: FAILED - $e');
      _log('_createNotificationChannel: stackTrace - $stackTrace');
    }
  }

  Future<dynamic> _onMethod(String name, dynamic args) async {
    _log('_onMethod called: $name');
    switch (name) {
      case "show_notification":
        final a = Map<String, dynamic>.from(args as Map);
        final result = await _showNotification(
          a["id"] as int,
          a["title"] as String,
          a["body"] as String,
          payload: a["payload"] as String? ?? "",
        );
        _log('_onMethod show_notification result: $result');
        return result;
      case "request_permissions":
        final granted = await _requestPermissions();
        _log('_onMethod request_permissions result: $granted');
        return granted.toString();
      case "check_permissions":
        final enabled = await _checkPermissions();
        _log('_onMethod check_permissions result: $enabled');
        return enabled.toString();
    }
    _log('_onMethod: unknown method $name');
    return null;
  }

  Future<String> _showNotification(int id, String title, String body,
      {String payload = ""}) async {
    _log('_showNotification: id=$id title=$title');

    final initialized = await _ensureInitialized();
    if (!initialized) {
      _log('_showNotification: plugin not initialized, aborting');
      return "error:not_initialized";
    }

    // Check permission before showing - Android 13+ silently drops
    // notifications without POST_NOTIFICATIONS, and _plugin.show()
    // returns without error even when permission is missing.
    try {
      final android = _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
      if (android != null) {
        final enabled = await android.areNotificationsEnabled();
        if (enabled != null && !enabled) {
          _log('_showNotification: notifications not permitted, requesting');
          final granted = await android.requestNotificationsPermission();
          if (granted != true) {
            _log('_showNotification: permission denied by user');
            return "error:no_permission";
          }
          _log('_showNotification: permission granted');
        }
      }
    } catch (e) {
      _log('_showNotification: permission check failed - $e');
    }

    _lastShowTime = DateTime.now();

    try {
      const androidDetails = AndroidNotificationDetails(
        'trebnic_reminders',
        'Task reminders',
        channelDescription: 'Task reminders from Trebnic',
        importance: Importance.high,
        priority: Priority.high,
        playSound: true,
        enableVibration: true,
      );
      const details = NotificationDetails(android: androidDetails);

      await _plugin.show(id, title, body, details, payload: payload);
      _log('_showNotification: _plugin.show() completed successfully');
      return "ok";
    } catch (e, stackTrace) {
      _log('_showNotification: FAILED - $e');
      _log('_showNotification: stackTrace - $stackTrace');
      return "error:show_failed:$e";
    }
  }

  Future<bool> _requestPermissions() async {
    _log('_requestPermissions: requesting');
    await _ensureInitialized();

    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (android == null) {
      _log('_requestPermissions: not on Android');
      return false;
    }

    try {
      final granted = await android.requestNotificationsPermission();
      _log('_requestPermissions: result=$granted');
      return granted ?? false;
    } catch (e, stackTrace) {
      _log('_requestPermissions: FAILED - $e');
      _log('_requestPermissions: stackTrace - $stackTrace');
      return false;
    }
  }

  Future<bool> _checkPermissions() async {
    _log('_checkPermissions: checking');
    await _ensureInitialized();

    final android = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (android == null) {
      _log('_checkPermissions: not on Android');
      return false;
    }

    try {
      final enabled = await android.areNotificationsEnabled();
      _log('_checkPermissions: enabled=$enabled');
      return enabled ?? false;
    } catch (e, stackTrace) {
      _log('_checkPermissions: FAILED - $e');
      _log('_checkPermissions: stackTrace - $stackTrace');
      return false;
    }
  }
}
