; Python function and method calls
; Extracts: call nodes with function names and attribute access chains

; Simple function call: func()
(call
  function: (identifier) @name)

; Method call: obj.method()
(call
  function: (attribute
    object: (identifier) @object
    attribute: (identifier) @method))

; Chained method calls: obj.method1().method2()
(call
  function: (attribute
    object: (call) @chained_call
    attribute: (identifier) @method))

; Nested attribute access: obj.attr1.attr2()
(call
  function: (attribute
    object: (attribute
      object: (identifier) @object
      attribute: (identifier) @attr1)
    attribute: (identifier) @attr2))

; Method call with subscript: obj[key].method()
(call
  function: (attribute
    object: (subscript) @subscript_obj
    attribute: (identifier) @method))

; Calls with arguments capture
(call
  function: (identifier) @name
  arguments: (argument_list) @arguments)

; Built-in function calls like print(), len(), etc.
(call
  function: (identifier) @builtin_call)

; Calls on literal values like [].append()
(call
  function: (attribute
    object: (list) @list_literal
    attribute: (identifier) @method))

; Calls on dict literals like {}.get()
(call
  function: (attribute
    object: (dictionary) @dict_literal
    attribute: (identifier) @method))

; Calls with keyword arguments
(call
  function: (identifier) @name
  arguments: (argument_list
    (keyword_argument) @kwargs))
