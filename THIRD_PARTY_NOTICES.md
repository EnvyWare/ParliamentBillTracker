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

The visual identity, wording, layout, colour system, and typography of this
project are original work and do not reproduce the creative expression of the
inspiration video or its accompanying poster.

## Software dependencies

Runtime dependencies are deliberately minimal.

- The ingestion Lambda uses only the Python standard library plus `boto3`,
  which is provided by the AWS Lambda Python runtime
  (Apache License 2.0).
- The frontend ships no third-party runtime library other than React and
  React DOM (MIT). No remote font, analytics script, image, or charting
  library is loaded at runtime.

Development and build tooling licences are recorded in `frontend/package-lock.json`
and `backend/pyproject.toml`.
