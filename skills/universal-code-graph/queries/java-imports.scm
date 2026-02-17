; Java import statements
; Extracts: import_declaration nodes

; Simple import: import package.Class;
(import_declaration
  (scoped_identifier
    (scoped_identifier) @package
    (identifier) @class_name))

; Import with wildcard: import package.*;
(import_declaration
  (scoped_identifier) @package
  "*" @wildcard)

; Static import: import static package.Class.method;
(import_declaration
  "static" @static_keyword
  (scoped_identifier) @class_or_method)

; Static import with wildcard: import static package.Class.*;
(import_declaration
  "static" @static_keyword
  (scoped_identifier) @class_name
  "*" @wildcard)

; Import single identifier (rare but valid)
(import_declaration
  (identifier) @name)

; Capture full import path
(import_declaration) @import_statement

; Capture modules from import paths
(scoped_identifier
  (scoped_identifier) @parent_module
  (identifier) @child_module)

; Capture nested scoped identifiers
(scoped_identifier
  (identifier) @module)

; Package declarations (for context)
(package_declaration
  (scoped_identifier) @package_name)

; Fully qualified type references within code (for dependency analysis)
(type_identifier) @type_reference
