{
  description = "Orefox MINDS / ollama integration proof-of-concept flake";
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
        pypiPackages = with pkgs.python313Packages; [
          ollama
          django
          django-htmx
          pillow
          psycopg2-binary
          django-environ
          django-storages
          python-dotenv
          typing
          pydantic
        ];

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
        pythonWithPackages = pkgs.python313.withPackages (p: [ pypiPackages ]);
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
            openssl.dev

            ollama
            patchedPgPostGIS
            pythonWithPackages
            pypiPackages

            postgres-lsp
            ruff
            pyright
          ];

          shellHook = ''
            export PKG_CONFIG_PATH=${pkgs.openssl.dev}/lib/pkgconfig":$PKG_CONFIG_PATH"
            export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$NIX_LD_LIBRARY_PATH
            export PGHOST="$PWD/.pg-sock"
            export PGDATA="$PWD/.pg-data"
            export PATH=${patchedPgPostGIS}/bin:"$PATH"

            if [ ! -f ".pg-data/PG_VERSION" ]; then
              mkdir -p "$PGHOST"
              mkdir -p "$PGDATA"

              initdb -U postgres -D "$PGDATA"

              echo "unix_socket_directories = '$PWD/.pg-sock'" >> .pg-data/postgresql.conf
              echo "port = 5432" >> .pg-data/postgresql.conf

            fi

            echo "============================================================"
            echo "in shell"
            echo ""
            echo "  start postgres:"
            echo '      pg_ctl -D $PGDATA -l $PGDATA/logfile start'
            echo ""
            echo "  create new a db with postGIS extension:"
            echo '      psql -U postgres -c "CREATE DATABASE kms_ollama;" && \'
            echo '      psql -U postgres -d kms_ollama -c "CREATE EXTENSION postgis;"'
            echo ""
          '';
        };

      }
    );
}
