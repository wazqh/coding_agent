export interface GatewayCommand {
  file: string;
  args: string[];
}

export interface GatewayReady {
  origin: string;
  capability: string;
}

export type GatewayState = "idle" | "starting" | "ready" | "stopping" | "stopped" | "failed";

export interface DesktopRuntimeInfo {
  platform: NodeJS.Platform;
  gatewayState: GatewayState;
}

export interface ProviderCredentialInput {
  provider: string;
  apiKey: string;
}

export interface ProviderCredentialCopyInput {
  sourceProvider: string;
  targetProvider: string;
}

export interface CredentialSaveResult {
  persisted: boolean;
  backend: string;
  transactionId: string;
}

export interface RestartGatewayInput {
  workspace?: string;
  sessionId?: string;
  probeModel?: boolean;
}

export interface ForgeDesktopBridge {
  runtimeInfo(): Promise<DesktopRuntimeInfo>;
  selectWorkspace(): Promise<string | null>;
  saveProviderCredential(input: ProviderCredentialInput): Promise<CredentialSaveResult>;
  copyProviderCredential(input: ProviderCredentialCopyInput): Promise<CredentialSaveResult>;
  commitProviderCredential(transactionId: string): Promise<boolean>;
  rollbackProviderCredential(transactionId: string): Promise<boolean>;
  deleteProviderCredential(provider: string): Promise<void>;
  restartGateway(input?: RestartGatewayInput): Promise<void>;
  openExternal(url: string): Promise<boolean>;
  minimize(): void;
  toggleMaximize(): void;
  close(): void;
}
