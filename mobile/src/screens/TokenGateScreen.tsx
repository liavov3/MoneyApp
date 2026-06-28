// Minimal dev token gate. The backend authenticates with a static dev bearer
// token (no email/password yet — MOBILE_UI_UX_SPEC §4.A). Paste once; it is
// stored in SecureStore. No signup / reset / onboarding.
import React, { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { setToken } from '../api';
import { AppText, Button } from '../components/ui';
import { colors, font, radius, spacing } from '../theme';

export default function TokenGateScreen({ onReady }: { onReady: () => void }) {
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);

  async function onContinue() {
    if (!value.trim()) return;
    setSaving(true);
    try {
      await setToken(value);
      onReady();
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.container}>
      <AppText size={font.heading} weight="700" style={{ marginBottom: spacing.sm }}>
        כניסה
      </AppText>
      <AppText color={colors.textSecondary} style={{ marginBottom: spacing.xl }}>
        הזן את אסימון הגישה כדי להתחבר לחשבון.
      </AppText>
      <TextInput
        value={value}
        onChangeText={setValue}
        placeholder="אסימון גישה"
        placeholderTextColor={colors.muted}
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
        style={styles.input}
      />
      <Button title={saving ? 'מתחבר…' : 'המשך'} onPress={onContinue} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: spacing.xl },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    color: colors.textPrimary,
    borderRadius: radius.input,
    padding: spacing.lg,
    fontSize: font.body,
    textAlign: 'right',
    marginBottom: spacing.lg,
  },
});
