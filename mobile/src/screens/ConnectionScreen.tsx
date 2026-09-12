import { Ionicons } from '@expo/vector-icons';
import React, { useState, useSyncExternalStore } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError, createApiClient } from '../api';
import { AppText, Button, Card, Input, Screen } from '../components/ui';
import { configuredApiUrl, session } from '../session';
import { ConnectionError, normalizeBaseUrl } from '../sessionStore';
import { colors, font, spacing, weight } from '../theme';

export function ConnectionScreen() {
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const [token, setToken] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const insets = useSafeAreaInsets();
  let server = '';
  try { server = normalizeBaseUrl(configuredApiUrl); } catch { /* No malformed URL details shown. */ }

  const connect = async () => {
    if (state.busy || !token.trim()) return;
    setMessage(null);
    try {
      await session.connect(token, async (credentials) => {
        const result = await createApiClient({ getConnection: () => credentials, invalidate: () => {} }).getCategories();
        if (!Array.isArray(result.items)) throw new Error('invalid_response');
      });
      setToken('');
    } catch (error) {
      setMessage(
        error instanceof ApiError && error.status === 401 ? 'קוד הגישה לא תקין. בדוק אותו ונסה שוב.'
          : error instanceof ConnectionError && error.code === 'invalid_token' ? 'יש להדביק את קוד הגישה בלבד, ללא רווחים.'
          : error instanceof ConnectionError && error.code === 'invalid_url' ? 'כתובת השרת לא הוגדרה כראוי.'
          : error instanceof ConnectionError && error.code === 'storage_write' ? 'החיבור הצליח, אבל לא הצלחנו לשמור אותו במכשיר. נסה שוב.'
          : 'לא הצלחנו להתחבר. בדוק שהשרת זמין ושהמכשיר מחובר לרשת המתאימה.',
      );
    }
  };

  return (
    <Screen>
      <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xl }]}>
          <View style={styles.heading}>
            <Ionicons name="lock-closed-outline" size={38} color={colors.accent} />
            <AppText size={font.h1} weight={weight.bold} align="center">
              {state.status === 'expired' ? 'חיבור מחדש' : 'התחברות ל־MoneySaver'}
            </AppText>
            <AppText color={colors.textSecondary} align="center">
              {state.status === 'expired' ? 'נדרש קוד גישה עדכני. הטופס הפתוח נשמר כאן.' : 'הזן את קוד הגישה לשרת האישי שלך כדי להתחיל.'}
            </AppText>
          </View>
          <Card style={styles.form}>
            {server ? <AppText size={font.caption} color={colors.textMuted} style={styles.server}>{server}</AppText> : null}
            <AppText weight={weight.medium}>קוד גישה</AppText>
            <Input value={token} onChangeText={setToken} accessibilityLabel="קוד גישה" placeholder="הדבק את קוד הגישה"
              secureTextEntry autoCapitalize="none" autoCorrect={false} autoComplete="off" textContentType="none"
              editable={!state.busy} returnKeyType="go" onSubmitEditing={() => { void connect(); }}
              style={styles.server} iconLeft="key-outline" />
            {message ? <AppText color={colors.danger}>{message}</AppText> : null}
            {state.error ? (
              <AppText color={colors.danger}>
                {state.error === 'storage_clear'
                  ? 'החיבור הוסתר, אבל לא הצלחנו להסיר את הקוד השמור. נסה שוב לפני סגירת האפליקציה.'
                  : 'לא הצלחנו לקרוא את החיבור השמור. אפשר לנסות שוב או להזין את הקוד מחדש.'}
              </AppText>
            ) : null}
            <Button title="התחברות" onPress={() => { void connect(); }} loading={state.busy} disabled={!token.trim()} />
            {state.error === 'storage_read' ? <Button title="טעינת החיבור מחדש" variant="ghost" disabled={state.busy} onPress={() => { void session.restore(); }} /> : null}
            {state.status === 'expired' || state.error === 'storage_clear' ? (
              <Button title="שכחת החיבור ויציאה" variant="ghost" disabled={state.busy} onPress={() => { void session.disconnect(); }} />
            ) : null}
            <AppText size={font.caption} color={colors.textMuted}>
              {Platform.OS === 'web' ? 'בתצוגת הדפדפן, החיבור נשמר רק עד לרענון או סגירת הדף.' : 'קוד הגישה נשמר באחסון המאובטח במכשיר.'}
            </AppText>
            {state.status === 'expired' ? <AppText size={font.caption} color={colors.textMuted}>יציאה סוגרת טפסים שלא נשמרו. עסקאות שנשמרו נשארות בשרת.</AppText> : null}
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { flexGrow: 1, justifyContent: 'center', padding: spacing.lg, gap: spacing.xl, width: '100%', maxWidth: 480, alignSelf: 'center' },
  heading: { alignItems: 'center', gap: spacing.md },
  form: { gap: spacing.md },
  server: { textAlign: 'left', writingDirection: 'ltr' },
});
