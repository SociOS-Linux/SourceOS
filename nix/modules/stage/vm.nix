{ lib, ... }:
{
  options.sourceos.stage.vm = {
    enable = lib.mkEnableOption "SourceOS stage VM lane";
    candidateRef = lib.mkOption {
      type = lib.types.str;
      default = ".#stage-vm";
      description = "Installable reference for the stage VM candidate.";
    };
  };
}
