{ lib, config, pkgs, ... }:

let
  cfg = config.sourceos.fog;
in {
  options.sourceos.fog = {
    enable = lib.mkEnableOption "SourceOS fog substrate invariants";

    hostRoot = lib.mkOption {
      type = lib.types.str;
      default = "/srv/fog";
      description = "Host-side root for the canonical fog directory contract.";
    };

    containerRoot = lib.mkOption {
      type = lib.types.str;
      default = "/mnt/fog";
      description = "Canonical in-container bind root for fog-aware workloads.";
    };

    vgName = lib.mkOption {
      type = lib.types.str;
      default = "vg_fog";
      description = "Default LVM volume-group name for fog-capable nodes/workstations.";
    };

    thinPoolName = lib.mkOption {
      type = lib.types.str;
      default = "thinpool_fog";
      description = "Default thin-pool name for fog-capable nodes/workstations.";
    };

    directories = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "projects"
        "models"
        "datasets"
        "topics"
        "vector"
        "cache"
        "logs"
        "secrets"
        "tmp"
      ];
      description = "Canonical fog directory set created beneath `hostRoot`.";
    };

    rootlessRuntime = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Whether the default fog execution posture assumes a rootless-capable container runtime.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = with pkgs; [
      lvm2
      util-linux
      jq
    ];

    systemd.tmpfiles.rules = map (name: "d ${cfg.hostRoot}/${name} 0755 root root - -") cfg.directories;

    assertions = [
      {
        assertion = cfg.hostRoot != cfg.containerRoot;
        message = "sourceos.fog.hostRoot and sourceos.fog.containerRoot must not be the same path.";
      }
    ];
  };
}
