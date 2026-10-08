// FILE MAP
//   10-20  ServerConfig: how the server was started
//   23-60  parseArgs: CLI flags -> ServerConfig (replay + dry-run by default)
//
// Purpose: the only place that decides mode and write permissions. Defaults are the safe ones:
// replay mode, no approval, empty allowlist.

import { homedir } from "node:os";
import { join } from "node:path";

export type Mode = "replay" | "live";

export interface ServerConfig {
  mode: Mode;
  approve: boolean; // writes are refused unless the operator passed --approve
  allowRepos: string[]; // owner/name repos live writes may ever touch
  replayDir: string;
  gitDir?: string; // directory of bare clones named <owner>__<name>.git, for get_file
}

export function parseArgs(argv: string[], env: NodeJS.ProcessEnv = process.env): ServerConfig {
  const cfg: ServerConfig = {
    mode: "replay",
    approve: false,
    allowRepos: [],
    // TWEAK: default bundle location written by `python -m evals.export_replay`
    replayDir: env.TRIAGEBENCH_REPLAY_DIR ?? join(homedir(), ".cache", "triagebench", "replay"),
    gitDir: env.TRIAGEBENCH_GIT_DIR,
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const next = (): string => {
      const v = argv[++i];
      if (v === undefined) throw new Error(`${arg} needs a value`);
      return v;
    };
    switch (arg) {
      case "--mode": {
        const m = next();
        if (m !== "replay" && m !== "live") throw new Error(`unknown mode ${m}`);
        cfg.mode = m;
        break;
      }
      case "--approve":
        cfg.approve = true;
        break;
      case "--allow-repo":
        cfg.allowRepos.push(next());
        break;
      case "--replay-dir":
        cfg.replayDir = next();
        break;
      case "--git-dir":
        cfg.gitDir = next();
        break;
      default:
        throw new Error(`unknown argument ${arg}`);
    }
  }
  return cfg;
}
