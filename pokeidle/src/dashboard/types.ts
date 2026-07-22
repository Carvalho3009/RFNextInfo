export type AutomationState =
  | "BOOT"
  | "AUTH_CHECK"
  | "LOGIN_REQUIRED"
  | "LOAD_GAME"
  | "VERIFY_CHARACTER"
  | "VERIFY_HUNT"
  | "CONFIGURE_NATIVE_HELPERS"
  | "START_OR_RESUME_HUNT"
  | "MONITOR_COMBAT"
  | "RECOVER_FROM_FAINT"
  | "RECOVER_CONNECTION"
  | "SESSION_EXPIRED"
  | "SAFE_STOP"
  | "ERROR_BACKOFF";

export interface MetricSample {
  at: string;
  nodeRssMb: number;
  nodeHeapMb: number;
  chromiumRssMb: number | null;
  chromiumCpuPercent: number | null;
  jsHeapMb: number | null;
  domNodes: number | null;
  websocketCount: number;
}

export interface GameObservation {
  contractComplete: boolean;
  gameReady: boolean | null;
  loginRequired: boolean | null;
  characterPresent: boolean | null;
  characterFainted: boolean | null;
  hpPercent: number | null;
  huntActive: boolean | null;
  suppliesMissing: boolean | null;
  autoPotionEnabled: boolean | null;
  autoReviveEnabled: boolean | null;
  connected: boolean;
}

export interface InstanceStatus {
  id: string;
  accountLabel: string;
  environment: string;
  state: AutomationState;
  tone: "healthy" | "stopped" | "attention" | "error";
  running: boolean;
  pid: number | null;
  startedAt: string | null;
  lastHeartbeat: string | null;
  reason: string | null;
  restartCount: number;
  circuitOpenUntil: string | null;
  observation: GameObservation | null;
  latestMetric: MetricSample | null;
  metrics: MetricSample[];
}
