# Third-party notices

## UK Parliament data

Source: [UK Parliament Bills API](https://developer.parliament.uk/)

> Contains Parliamentary information licensed under the
> [Open Parliament Licence v3.0](https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/).

The repository's MIT licence applies to the project's original software and
project-created assets, not to Parliamentary information. This project is
unofficial and is not endorsed by UK Parliament.

Parliamentary information retrieved by this project is published as a
normalised JSON snapshot at `/data/current.json`. That snapshot, and any
test fixture in this repository derived from real API responses, is covered
by the Open Parliament Licence v3.0 and is **excluded from the MIT grant**.

The Open Parliament Licence does not cover, and this project therefore does
not use, the Crowned Portcullis, the Royal Arms, UK Parliament logos or
wordmarks, Parliamentary photography, broadcast footage, or archive imagery.
Member photograph URLs returned by the API are deliberately discarded during
normalisation and are never published or proxied by this project.

## Inspiration

The project concept was inspired by TLDR News's
[How Bills Get Passed in Parliament (and why it takes so long)](https://www.youtube.com/watch?v=pLSE3O5OaBo).
No TLDR News video, audio, transcript, thumbnail, poster, illustrations, or
other assets are included.

The wording, layout, and diagrams of this project are original work, and the
visual identity is EnvyWare's own brand system (see below). Neither reproduces
the creative expression of the inspiration video or its accompanying poster.

## EnvyWare brand assets

The EnvyWare name, the Prompt E mark, the ENVYWARE wordmark, and the icon and
favicon files derived from them are brand assets of EnvyWare Ltd. They appear
here because this is an EnvyWare project.

They are **excluded from the MIT grant**. The MIT licence gives you the code;
it does not give you permission to use EnvyWare's name or marks to identify
your own work, or to suggest that EnvyWare endorses it. If you fork this
project, replace the mark in `frontend/src/components/EnvyWareMark.tsx`, the
files in `frontend/public/` that are derived from it, and the brand colours
in `frontend/src/styles/tokens.css`.

Everything else in the frontend, including the flow diagram geometry and the
layout, is MIT like the rest of the project's own code.

## Software dependencies

Runtime dependencies are deliberately minimal.

- The ingestion Lambda uses only the Python standard library plus `boto3`,
  which is provided by the AWS Lambda Python runtime
  (Apache License 2.0).
- The frontend ships no third-party runtime library other than React and
  React DOM (MIT). No remote font, analytics script, image, or charting
  library is loaded at runtime.

### Bundled fonts

Two typefaces are served from this origin rather than from a font CDN, so
that no third party sees a request from anyone reading the site. Both are
under the [SIL Open Font License 1.1](https://openfontlicense.org/), which
permits redistribution as part of a larger work:

| Font | Files | Copyright |
| --- | --- | --- |
| Poppins | `frontend/public/fonts/poppins-latin-v24.woff2` | Indian Type Foundry, Jonny Pinhorn |
| Inter | `frontend/public/fonts/inter-latin-v20.woff2` | Rasmus Andersson |

Both are the latin subsets only, unmodified apart from that subsetting. They
are **not** covered by the MIT grant; the Open Font License travels with the
font files themselves.

Development and build tooling licences are recorded in `frontend/package-lock.json`
and `backend/pyproject.toml`.
