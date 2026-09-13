import { Ionicons } from '@expo/vector-icons';
import React, { useState, useSyncExternalStore } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { SignInError } from '../authClient';
import { AppText, Button, Card, Input, Screen } from '../components/ui';
import { session } from '../session';
import { ConnectionError } from '../sessionStore';
import { colors, font, spacing, weight } from '../theme';

export function ConnectionScreen() {
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const insets = useSafeAreaInsets();

  const connect = async () => {
    if (state.busy || !username.trim() || !password) return;
    setMessage(null);
    try {
      await session.signIn(username, password);
      setPassword('');
    } catch (error) {
      setMessage(
        error instanceof SignInError && (error.status === 401 || error.status === 422) ? 'שם המשתמש או הסיסמה אינם נכונים.'
          : error instanceof SignInError && error.status === 429 ? 'בוצעו ניסיונות התחברות רבים. אפשר לנסות שוב בעוד דקה.'
          : error instanceof ConnectionError && error.code === 'invalid_url' ? 'כתובת השרת לא הוגדרה כראוי.'
          : error instanceof ConnectionError && error.code === 'storage_write' ? 'החיבור הצליח, אבל לא הצלחנו לשמור אותו במכשיר. נסה שוב.'
          : 'לא הצלחנו להתחבר. בדוק את החיבור לאינטרנט ונסה שוב.',
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
              {state.status === 'expired' ? 'התחברות מחדש' : 'ברוך הבא ל־MoneySaver'}
            </AppText>
            <AppText color={colors.textSecondary} align="center">
              {state.status === 'expired' ? 'יש להתחבר שוב. הטופס הפתוח נשמר כאן.' : 'המקום הפרטי שלך לניהול הכסף.'}
            </AppText>
          </View>
          <Card style={styles.form}>
            <AppText weight={weight.medium}>שם משתמש</AppText>
            <Input value={username} onChangeText={setUsername} accessibilityLabel="שם משתמש" placeholder="שם המשתמש שלך"
              autoCapitalize="none" autoCorrect={false} autoComplete="username" textContentType="username"
              editable={!state.busy} maxLength={80} style={styles.server} iconLeft="person-outline" />
            <AppText weight={weight.medium}>סיסמה</AppText>
            <Input value={password} onChangeText={setPassword} accessibilityLabel="סיסמה" placeholder="הסיסמה שלך"
              secureTextEntry autoCapitalize="none" autoCorrect={false} autoComplete="current-password" textContentType="password" maxLength={128}
              editable={!state.busy} returnKeyType="go" onSubmitEditing={() => { void connect(); }}
              style={styles.server} iconLeft="lock-closed-outline" />
            {message ? <AppText color={colors.danger}>{message}</AppText> : null}
            {state.error ? (
              <AppText color={colors.danger}>
                {state.error === 'storage_clear'
                  ? 'לא הצלחנו להסיר את החיבור השמור מהמכשיר. יש לנסות שוב.'
                  : state.error === 'logout' ? 'היציאה לא הושלמה. בדוק את החיבור ונסה שוב.'
                  : 'לא הצלחנו לבדוק את ההתחברות השמורה. אפשר לנסות שוב או להתחבר מחדש.'}
              </AppText>
            ) : null}
            <Button title="התחברות" onPress={() => { void connect(); }} loading={state.busy} disabled={!username.trim() || !password} />
            {state.busy ? <AppText size={font.caption} color={colors.textMuted}>מתחבר… הפתיחה הראשונה עשויה לקחת עד דקה.</AppText> : null}
            {state.error === 'storage_read' ? <Button title="טעינת החיבור מחדש" variant="ghost" disabled={state.busy} onPress={() => { void session.restore(); }} /> : null}
            {state.status === 'expired' || state.error === 'storage_clear' ? (
              <Button title="יציאה" variant="ghost" disabled={state.busy} onPress={() => { void session.disconnect(); }} />
            ) : null}
            <AppText size={font.caption} color={colors.textMuted}>
              ההתחברות נשמרת במכשיר האישי שלך עד 30 יום. ניתן לצאת בכל רגע דרך ההגדרות.
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
