# Same failing call: before and after

## Before: opaque server error

Call: `get_deprecation_notice(package=acme-sdk, version=4.0)`

Server response: `Error 3: not found`

Model handling: cannot distinguish an unknown future version from an outage; it may guess an API.

## After: docstring-as-prompt and recoverable error

Call: `get_deprecation_notice(package=acme-sdk, version=4.0)`

Server response: `No deprecation record for acme-sdk 4.0; latest published is 3.2.0. Ask for a valid version or use the latest release.`

Model handling: explain that v4.0 is not published, use latest 3.2.0 or ask the user for a valid version; do not invent v4 APIs.
