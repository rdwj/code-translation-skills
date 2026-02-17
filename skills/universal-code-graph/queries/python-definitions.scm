; Python function and class definitions
; Extracts: function_definition, class_definition with metadata

; Function definitions with name, parameters, and optional return type annotation
(function_definition
  name: (identifier) @name
  parameters: (parameters
    (parameter) @parameter)
  return_type: (type) @return_type)

; Function definitions without return type
(function_definition
  name: (identifier) @name
  parameters: (parameters) @parameters)

; Class definitions with name, bases, and decorators
(class_definition
  name: (identifier) @name
  superclasses: (argument_list) @bases)

; Class definitions without bases
(class_definition
  name: (identifier) @name)

; Decorators for functions and classes
(decorator
  "@" @decorator_prefix
  (identifier) @decorator_name)

; Decorated functions
(decorated_definition
  decorators: (decorator) @decorator
  definition: (function_definition
    name: (identifier) @name))

; Decorated classes
(decorated_definition
  decorators: (decorator) @decorator
  definition: (class_definition
    name: (identifier) @name))

; Async function definitions
(function_definition
  "async" @async_keyword
  name: (identifier) @name)

; Method definitions within classes (captured at function_definition level)
; The parent context will distinguish between module-level and class-level
