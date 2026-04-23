{ lib, ... }:
{
  options.sourceos.storage.mounts = lib.mkOption {
    type = lib.types.listOf lib.types.attrs;
    default = [ ];
    description = "Declared mount classes for SourceOS substrate lanes.";
  };
}
