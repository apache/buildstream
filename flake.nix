{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixpkgs-unstable";
    flake-compat.url = "https://flakehub.com/f/edolstra/flake-compat/1.tar.gz";
  };

  outputs = inputs: let
    inherit (inputs) self nixpkgs;
    forAllSystems = function:
      nixpkgs.lib.genAttrs [
        "x86_64-linux"
        "aarch64-linux"
      ] (system:
        function (import nixpkgs {
          inherit system;
          overlays = [
            (_: prev: {
              buildstream = prev.buildstream.overrideAttrs (_: {
                version = "git";
                src = self;
              });
            })
          ];
        }));
  in {
    devShells = forAllSystems (pkgs: {
      default = pkgs.mkShell {
        inputsFrom = [pkgs.buildstream];
      };
    });

    packages = forAllSystems (pkgs: {
      inherit (pkgs) buildstream;
      default = self.packages.${pkgs.system}.buildstream;
    });

    overlays.default = _final: prev: {
      inherit (self.packages.${prev.system}) buildstream;
    };
  };
}
