export interface PayloadSwitchGuard {
  begin(): number;
  finish(token: number): void;
  isCurrent(token: number): boolean;
  isSwitching(): boolean;
}

export function createPayloadSwitchGuard(): PayloadSwitchGuard {
  let sequence = 0;
  let activeToken: number | null = null;

  return {
    begin() {
      sequence += 1;
      activeToken = sequence;
      return sequence;
    },
    finish(token: number) {
      if (activeToken === token) {
        activeToken = null;
      }
    },
    isCurrent(token: number) {
      return activeToken === token;
    },
    isSwitching() {
      return activeToken !== null;
    },
  };
}
