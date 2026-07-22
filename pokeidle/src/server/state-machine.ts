import type { AutomationState, GameObservation } from "./types.js";

export interface TransitionContext {
  rulesAcknowledged: boolean;
  contractComplete: boolean;
  observation: GameObservation | null;
  nativeHelpersConfigured: boolean;
  recoveryAttempts: number;
  maxRecoveryAttempts: number;
}

export interface TransitionDecision {
  state: AutomationState;
  reason: string | null;
}

const stay = (state: AutomationState, reason: string | null = null): TransitionDecision => ({ state, reason });

export function decideNextState(
  current: AutomationState,
  context: TransitionContext,
): TransitionDecision {
  const observation = context.observation;
  if (current === "SAFE_STOP") return stay("SAFE_STOP", "Intervenção do operador necessária");
  if (!context.rulesAcknowledged) {
    return stay("SAFE_STOP", "Regras oficiais sobre automação ainda não foram confirmadas");
  }
  if (!context.contractComplete) return stay("SAFE_STOP", "Contrato DOM autenticado incompleto");
  if (current === "BOOT") return stay("AUTH_CHECK");
  if (!observation) return stay("ERROR_BACKOFF", "Observação do cliente indisponível");
  if (current === "SESSION_EXPIRED") return stay("SAFE_STOP", "Sessão expirada; login manual necessário");
  if (current === "LOGIN_REQUIRED") return stay("SAFE_STOP", "Provisione a sessão manualmente; senha não é automatizada");
  if (observation.loginRequired === true) {
    return current === "AUTH_CHECK"
      ? stay("LOGIN_REQUIRED", "Login manual necessário")
      : stay("SESSION_EXPIRED", "Sessão persistente expirou");
  }
  if (!observation.connected && current !== "RECOVER_CONNECTION") {
    return stay("RECOVER_CONNECTION", "Cliente desconectado");
  }

  switch (current) {
    case "AUTH_CHECK":
      return observation.gameReady === true
        ? stay("LOAD_GAME")
        : stay("ERROR_BACKOFF", "Cliente ainda não está pronto");
    case "LOGIN_REQUIRED":
      return stay("SAFE_STOP", "Login manual necessário");
    case "LOAD_GAME":
      return stay("VERIFY_CHARACTER");
    case "VERIFY_CHARACTER":
      if (observation.characterPresent !== true) {
        return stay("SAFE_STOP", "Personagem não identificado de forma única");
      }
      if (observation.hpPercent === null) return stay("SAFE_STOP", "HP não identificado pelo contrato DOM");
      return observation.characterFainted === true
        ? stay("RECOVER_FROM_FAINT", "Personagem derrotado")
        : stay("VERIFY_HUNT");
    case "VERIFY_HUNT":
      return stay("CONFIGURE_NATIVE_HELPERS");
    case "CONFIGURE_NATIVE_HELPERS":
      if (!context.nativeHelpersConfigured) return stay("CONFIGURE_NATIVE_HELPERS");
      return observation.huntActive === true
        ? stay("MONITOR_COMBAT")
        : stay("START_OR_RESUME_HUNT");
    case "START_OR_RESUME_HUNT":
      return observation.huntActive === true
        ? stay("MONITOR_COMBAT")
        : stay("START_OR_RESUME_HUNT", "Aguardando confirmação da hunt");
    case "MONITOR_COMBAT":
      if (observation.characterPresent !== true || observation.hpPercent === null) {
        return stay("SAFE_STOP", "Contrato DOM do personagem divergiu");
      }
      if (observation.autoPotionEnabled === null || observation.autoReviveEnabled === null) {
        return stay("SAFE_STOP", "Estado dos helpers nativos ficou ambíguo");
      }
      if (observation.suppliesMissing === true) {
        return stay("SAFE_STOP", "Suprimentos insuficientes; compra automática não autorizada");
      }
      if (observation.characterFainted === true) return stay("RECOVER_FROM_FAINT", "Personagem derrotado");
      if (!context.nativeHelpersConfigured) return stay("CONFIGURE_NATIVE_HELPERS", "Helper nativo deixou de estar confirmado");
      if (observation.huntActive !== true) return stay("VERIFY_HUNT", "Hunt deixou de estar ativa");
      return stay("MONITOR_COMBAT");
    case "RECOVER_FROM_FAINT":
      if (observation.suppliesMissing === true) {
        return stay("SAFE_STOP", "Revive indisponível e compras automáticas proibidas");
      }
      if (observation.characterFainted === false) return stay("VERIFY_CHARACTER");
      if (context.recoveryAttempts >= context.maxRecoveryAttempts) {
        return stay("SAFE_STOP", "Recuperação do personagem excedeu o limite");
      }
      return stay("RECOVER_FROM_FAINT");
    case "RECOVER_CONNECTION":
      if (observation.connected) return stay("AUTH_CHECK");
      if (context.recoveryAttempts >= context.maxRecoveryAttempts) {
        return stay("ERROR_BACKOFF", "Reconexão excedeu o limite");
      }
      return stay("RECOVER_CONNECTION");
    case "SESSION_EXPIRED":
      return stay("SAFE_STOP", "Sessão expirada");
    case "ERROR_BACKOFF":
      return stay("AUTH_CHECK");
    case "BOOT":
    case "SAFE_STOP":
      return stay(current);
  }
}
