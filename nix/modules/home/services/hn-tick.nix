{ lib, pkgs, config, ... }:
let
  cfg = config.sourceos.services.hnTick;
in
{
  options.sourceos.services.hnTick = {
    enable = lib.mkEnableOption "hn-tick service";
    stateDir = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/state/hn-tick";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.user.services.hn-tick = {
      Unit.Description = "SourceOS hn-tick service";
      Service = {
        Type = "simple";
        ExecStart = "${pkgs.coreutils}/bin/true";
        WorkingDirectory = cfg.stateDir;
      };
      Install.WantedBy = [ "default.target" ];
    };
  };
}
