{
  description = "SourceOS substrate scaffold for Fedora Asahi + Nix control-plane lanes";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-linux" "x86_64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in {
      formatter = forAllSystems (system:
        let pkgs = import nixpkgs { inherit system; };
        in pkgs.nixfmt-rfc-style
      );

      devShells = forAllSystems (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            packages = with pkgs; [
              git
              jq
              yq-go
              nixfmt-rfc-style
            ];
            shellHook = ''
              echo "SourceOS substrate dev shell (${system})"
              echo "This shell is the bootstrap surface for Fedora Asahi + Nix control-plane work."
            '';
          };
        }
      );
    };
}
