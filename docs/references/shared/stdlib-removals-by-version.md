# Standard Library Removals by Python Version

## Modules Removed in Python 3.12

These modules were deprecated in Python 3.11 and removed entirely in 3.12.
Any code importing these will fail on Python 3.12+.

| Module | Replacement | Notes |
|--------|------------|-------|
| `aifc` | No direct replacement | Use `soundfile` or `pydub` for audio I/O |
| `audioop` | No direct replacement | Use `pydub` or `numpy` for audio processing |
| `cgi` | `urllib.parse.parse_qs`, `email.message` | For form parsing; `http.server` for CGI serving |
| `cgitb` | `traceback`, `faulthandler` | For detailed tracebacks |
| `chunk` | No direct replacement | Implement IFF chunk reading manually or use specialized libs |
| `crypt` | `bcrypt`, `passlib`, `hashlib` | For password hashing |
| `imghdr` | `filetype`, `python-magic`, `Pillow` | For image type detection |
| `mailcap` | No direct replacement | Rarely needed; use `mimetypes` for MIME type mapping |
| `msilib` | No direct replacement | Windows MSI creation; use `WiX` toolset instead |
| `nis` | No direct replacement | NIS/YP client; rarely needed in modern systems |
| `nntplib` | No direct replacement | NNTP client; use third-party NNTP libraries |
| `ossaudiodev` | No direct replacement | Linux OSS audio; use `pyaudio` or `sounddevice` |
| `pipes` | `subprocess`, `shlex` | For shell pipeline construction |
| `sndhdr` | `filetype`, `python-magic` | For sound file type detection |
| `spwd` | No direct replacement | Shadow password database; use PAM or OS-level auth |
| `sunau` | No direct replacement | Sun AU audio format; use `soundfile` |
| `telnetlib` | `telnetlib3`, `asynctelnet` | For Telnet client; use SSH when possible |
| `uu` | `base64`, `binascii` | For uuencode/uudecode |
| `xdrlib` | `struct`, `xdrlib2` | For XDR data serialization |

### distutils (Critical)

`distutils` was the original Python build system and is **removed in Python 3.12**.
This is often the single biggest blocker for targeting 3.12+.

| Old Import | Replacement |
|-----------|------------|
| `distutils.core.setup` | `setuptools.setup` |
| `distutils.core.Extension` | `setuptools.Extension` |
| `distutils.command.*` | `setuptools.command.*` |
| `distutils.sysconfig` | `sysconfig` (stdlib) |
| `distutils.util.strtobool` | Implement manually: `val.lower() in ('yes', 'true', '1')` |
| `distutils.version.LooseVersion` | `packaging.version.Version` |
| `distutils.version.StrictVersion` | `packaging.version.Version` |
| `distutils.dir_util` | `shutil` |
| `distutils.file_util` | `shutil` |
| `distutils.spawn.find_executable` | `shutil.which` |

## Modules Renamed in Python 3 (from Python 2)

These modules exist in Python 3 but under different names. Import statements must be updated.

| Python 2 Name | Python 3 Name |
|--------------|--------------|
| `ConfigParser` | `configparser` |
| `Queue` | `queue` |
| `SocketServer` | `socketserver` |
| `HTMLParser` | `html.parser` |
| `httplib` | `http.client` |
| `urlparse` | `urllib.parse` |
| `urllib2` | `urllib.request`, `urllib.error` |
| `cPickle` | `pickle` (C implementation auto-selected) |
| `cStringIO` | `io.StringIO`, `io.BytesIO` |
| `repr` | `reprlib` |
| `Tkinter` | `tkinter` |
| `thread` | `_thread` (prefer `threading`) |
| `commands` | `subprocess` |
| `copy_reg` | `copyreg` |
| `xmlrpclib` | `xmlrpc.client` |
| `BaseHTTPServer` | `http.server` |
| `SimpleHTTPServer` | `http.server` |
| `CGIHTTPServer` | `http.server` |
| `Cookie` | `http.cookies` |
| `cookielib` | `http.cookiejar` |
| `htmlentitydefs` | `html.entities` |
| `robotparser` | `urllib.robotparser` |
| `UserDict` | `collections.UserDict` |
| `UserList` | `collections.UserList` |
| `UserString` | `collections.UserString` |
| `DocXMLRPCServer` | `xmlrpc.server` |
| `SimpleXMLRPCServer` | `xmlrpc.server` |

## Python 3.13 Additional Changes

- `cgi` and `cgitb` removal finalized (were already removed in 3.12)
- `pathlib.Path` becomes abstract (affects custom subclasses)
- Additional C API removals (affects native extensions)
- Free-threaded mode (no GIL) available as experimental option
- JIT compiler (experimental)

## Python 3.10-3.11 Notable Changes

These versions didn't remove major stdlib modules but introduced features that
affect migration strategy:

**3.10**: Structural pattern matching (`match`/`case`), better error messages
**3.11**: `tomllib` added, exception groups, 10-60% performance improvement, `asyncio.TaskGroup`

## Impact Assessment Guide

When evaluating target version impact:

1. **Count usages, not just imports** — a single `import cgi` could mean 1 usage or 100
2. **Check transitive dependencies** — your code might not import `distutils` directly, but a dependency's `setup.py` might use it
3. **Consider the replacement effort** — replacing `cgi.FieldStorage` is more work than replacing `pipes.quote`
4. **Factor in testing** — each replacement needs its own test coverage
5. **Prefer 3.11 as initial target** if `distutils` or removed module usage is heavy — get on Py3 first, then upgrade to 3.12+ in a second phase
