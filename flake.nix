{
  description = "Orefox MINDS KMS Development Flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        postGISPatch = pkgs.postgresql17Packages.postgis.overrideAttrs (prev: {
          postInstall = (prev.postInstall or "") + ''
            find $out -name "postgis*" -type f -executable | while read script; do
              if head -1 "$script" | grep -q "/usr/bin/perl"; then
                substituteInPlace "$script" --replace "#!/usr/bin/perl" "#!${pkgs.perl}/bin/perl"
              fi
            done
          '';
        });
        patchedPgPostGIS = pkgs.postgresql_17.withPackages (p: [ postGISPatch ]);
      in
      {
        devShells.default = pkgs.mkShell {
          NIX_LD_LIBRARY_PATH =
            with pkgs;
            lib.makeLibraryPath [
              libffi
              openssl
              stdenv.cc.cc
              zlib
              libxcrypt

              gdal
              geos
            ];

          buildInputs = with pkgs; [
            # nodejs
            bun

            ruff
            pyright

            pkg-config
            openssl.dev

            patchedPgPostGIS
            postGISPatch

            uv
          ];

          shellHook = ''
            export PKG_CONFIG_PATH=${pkgs.openssl.dev}/lib/pkgconfig:$PKG_CONFIG_PATH
            export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$NIX_LD_LIBRARY_PATH

            export PGHOST="`pwd`/.pg-sock"
            export PGDATA="`pwd`/.pg-data"
            export PATH=$PATH:${patchedPgPostGIS}

            export UV_PROJECT=`pwd`

            if [ ! -f "$PGDATA/PG_VERSION" ]; then
              mkdir -p "$PGHOST"
              mkdir -p "$PGDATA"

              initdb -U postgres -D "$PGDATA"

              echo "unix_socket_directories = '$PWD/.pg-sock'" >> .pg-data/postgresql.conf
              echo "port = 5432" >> .pg-data/postgresql.conf
            fi
            
            UV_RUN_SCRIPT="$UV_PROJECT/.venv/util/manage-py"
            if [ ! -f "$UV_RUN_SCRIPT" ]; then  
              mkdir -p "$UV_PROJECT/.venv/util"

              printf '#!/usr/bin/env bash\nuv run %s/manage.py "$@"\n' "$(pwd)" > "$UV_RUN_SCRIPT"
              chmod +x "$UV_RUN_SCRIPT"
            fi

            PATH+=:$UV_PROJECT/.venv/util

            echo "===================================================================="
            echo "in shell"
            echo ""
            echo "  start postgres:"
            echo '      pg_ctl -D $PGDATA -l $PGDATA/logfile start'
            echo ""
            echo "  create new a db with postGIS extension:"
            echo '      psql -U postgres -c "CREATE DATABASE orefox;" && \'
            echo '      psql -U postgres -d orefox -c "CREATE EXTENSION postgis;"'
            echo ""
          '';
        };
      }
    );
}
