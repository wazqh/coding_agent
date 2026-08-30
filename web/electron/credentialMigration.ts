import { credentialNameToReference } from "./pythonCredentialBridge.js";

interface SharedCredentialWriter {
  set(reference: string, secret: string): Promise<{ persisted: boolean }>;
}

export async function migrateLegacyCredentials(
  credentials: Readonly<Record<string, string>>,
  shared: SharedCredentialWriter,
  removeLegacy: (name: string) => Promise<void>,
): Promise<Record<string, string>> {
  const fallback: Record<string, string> = {};
  for (const [name, secret] of Object.entries(credentials)) {
    try {
      const saved = await shared.set(credentialNameToReference(name), secret);
      if (!saved.persisted) throw new Error("credential is not persistent");
      await removeLegacy(name);
    } catch {
      fallback[name] = secret;
    }
  }
  return fallback;
}
