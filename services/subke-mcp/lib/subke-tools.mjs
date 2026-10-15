export const operations = [
  {
    "name": "list_orders",
    "description": "List orders",
    "method": "GET",
    "path": "/v1/orders",
    "inputSchema": {
      "type": "object",
      "properties": {
        "status": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "from_date": {
          "type": "string",
          "format": "date",
          "minLength": 1,
          "maxLength": 512
        },
        "to_date": {
          "type": "string",
          "format": "date",
          "minLength": 1,
          "maxLength": 512
        },
        "page": {
          "type": "integer",
          "minimum": 1
        },
        "per_page": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100
        }
      },
      "required": [],
      "additionalProperties": false
    },
    "scope": "orders:read"
  },
  {
    "name": "get_order",
    "description": "Get order",
    "method": "GET",
    "path": "/v1/orders/{id}",
    "inputSchema": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [
        "id"
      ],
      "additionalProperties": false
    },
    "scope": "orders:read"
  },
  {
    "name": "get_order_shipments",
    "description": "List shipments (parcels) for an order — incl. per-parcel items with batch/MHD/IN-REF and serial_numbers",
    "method": "GET",
    "path": "/v1/orders/{id}/shipments",
    "inputSchema": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [
        "id"
      ],
      "additionalProperties": false
    },
    "scope": "orders:read"
  },
  {
    "name": "get_order_serial_numbers",
    "description": "List serial numbers shipped for an order",
    "method": "GET",
    "path": "/v1/orders/{id}/serial-numbers",
    "inputSchema": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [
        "id"
      ],
      "additionalProperties": false
    },
    "scope": "orders:read"
  },
  {
    "name": "list_serial_numbers",
    "description": "Search serial numbers across all orders / inbounds",
    "method": "GET",
    "path": "/v1/serial-numbers",
    "inputSchema": {
      "type": "object",
      "properties": {
        "serial_number": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "product_id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "order_id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "status": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "page": {
          "type": "integer",
          "minimum": 1
        },
        "per_page": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100
        }
      },
      "required": [],
      "additionalProperties": false
    },
    "scope": "orders:read"
  },
  {
    "name": "list_stock",
    "description": "List stock",
    "method": "GET",
    "path": "/v1/stock",
    "inputSchema": {
      "type": "object",
      "properties": {
        "sku": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "warehouse_id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [],
      "additionalProperties": false
    },
    "scope": "stock:read"
  },
  {
    "name": "list_products",
    "description": "List products",
    "method": "GET",
    "path": "/v1/products",
    "inputSchema": {
      "type": "object",
      "properties": {},
      "required": [],
      "additionalProperties": false
    },
    "scope": "products:read"
  },
  {
    "name": "get_product",
    "description": "Get product with packaging levels",
    "method": "GET",
    "path": "/v1/products/{id}",
    "inputSchema": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [
        "id"
      ],
      "additionalProperties": false
    },
    "scope": "products:read"
  },
  {
    "name": "list_warehouses",
    "description": "List warehouses",
    "method": "GET",
    "path": "/v1/warehouses",
    "inputSchema": {
      "type": "object",
      "properties": {},
      "required": [],
      "additionalProperties": false
    },
    "scope": "stock:read"
  },
  {
    "name": "list_returns",
    "description": "List returns",
    "method": "GET",
    "path": "/v1/returns",
    "inputSchema": {
      "type": "object",
      "properties": {},
      "required": [],
      "additionalProperties": false
    },
    "scope": "returns:read"
  },
  {
    "name": "get_return",
    "description": "Get return",
    "method": "GET",
    "path": "/v1/returns/{id}",
    "inputSchema": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [
        "id"
      ],
      "additionalProperties": false
    },
    "scope": "returns:read"
  },
  {
    "name": "list_inbound_shipments",
    "description": "List inbound shipments",
    "method": "GET",
    "path": "/v1/inbound",
    "inputSchema": {
      "type": "object",
      "properties": {
        "external_ref": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [],
      "additionalProperties": false
    },
    "scope": "inbound:read"
  },
  {
    "name": "get_inbound",
    "description": "Get inbound + items + goods receipts + serial_numbers",
    "method": "GET",
    "path": "/v1/inbound/{id}",
    "inputSchema": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [
        "id"
      ],
      "additionalProperties": false
    },
    "scope": "inbound:read"
  },
  {
    "name": "get_inbound_arrivals",
    "description": "Per-arrival goods receipts (incl. batch/MHD/IN-REF), pallet/box units and serial numbers",
    "method": "GET",
    "path": "/v1/inbound/{id}/arrivals",
    "inputSchema": {
      "type": "object",
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [
        "id"
      ],
      "additionalProperties": false
    },
    "scope": "inbound:read"
  },
  {
    "name": "get_shipment",
    "description": "Lookup by tracking number",
    "method": "GET",
    "path": "/v1/shipments/{tracking}",
    "inputSchema": {
      "type": "object",
      "properties": {
        "tracking": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        }
      },
      "required": [
        "tracking"
      ],
      "additionalProperties": false
    },
    "scope": "orders:read"
  },
  {
    "name": "list_sub_customers",
    "description": "List sub-customers of the authenticated parent (filter via ?q=, ?page, ?per_page). Order/shipment payloads also include a nested sub_customer object when applicable.",
    "method": "GET",
    "path": "/v1/sub-customers",
    "inputSchema": {
      "type": "object",
      "properties": {
        "q": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "page": {
          "type": "integer",
          "minimum": 1
        },
        "per_page": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100
        }
      },
      "required": [],
      "additionalProperties": false
    },
    "scope": "orders:read"
  },
  {
    "name": "create_order",
    "description": "Create a real fulfillment order. Obtain the user's instruction with shipping address and items before calling. Never call as a connectivity test.",
    "method": "POST",
    "path": "/v1/orders",
    "inputSchema": {
      "type": "object",
      "properties": {
        "body": {
          "type": "object",
          "properties": {
            "order_number": {
              "type": "string",
              "description": "order_number",
              "minLength": 1,
              "maxLength": 4096
            },
            "shipping_first_name": {
              "type": "string",
              "description": "shipping_first_name",
              "minLength": 1,
              "maxLength": 4096
            },
            "shipping_last_name": {
              "type": "string",
              "description": "shipping_last_name",
              "minLength": 1,
              "maxLength": 4096
            },
            "shipping_street": {
              "type": "string",
              "description": "shipping_street",
              "minLength": 1,
              "maxLength": 4096
            },
            "shipping_zip": {
              "type": "string",
              "description": "shipping_zip",
              "minLength": 1,
              "maxLength": 4096
            },
            "shipping_city": {
              "type": "string",
              "description": "shipping_city",
              "minLength": 1,
              "maxLength": 4096
            },
            "shipping_country": {
              "type": "string",
              "description": "shipping_country",
              "minLength": 1,
              "maxLength": 4096
            },
            "items": {
              "type": "array",
              "minItems": 1,
              "items": {
                "type": "object",
                "properties": {
                  "product_id": {
                    "type": "string",
                    "description": "Subke product ID",
                    "minLength": 1,
                    "maxLength": 4096
                  },
                  "packaging_level_id": {
                    "type": "string",
                    "description": "Subke packaging level ID",
                    "minLength": 1,
                    "maxLength": 4096
                  },
                  "quantity": {
                    "type": "number",
                    "exclusiveMinimum": 0
                  }
                },
                "required": [
                  "product_id",
                  "packaging_level_id",
                  "quantity"
                ],
                "additionalProperties": true
              }
            }
          },
          "additionalProperties": true,
          "required": [
            "order_number",
            "shipping_first_name",
            "shipping_last_name",
            "shipping_street",
            "shipping_zip",
            "shipping_city",
            "shipping_country",
            "items"
          ]
        }
      },
      "required": [
        "body"
      ],
      "additionalProperties": false
    },
    "scope": "orders:write"
  },
  {
    "name": "announce_return",
    "description": "Announce a real return using the Subke payload. Changes live fulfillment data; use only when requested.",
    "method": "POST",
    "path": "/v1/returns",
    "inputSchema": {
      "type": "object",
      "properties": {
        "body": {
          "type": "object",
          "properties": {
            "tracking_number": {
              "type": "string",
              "description": "tracking_number",
              "minLength": 1,
              "maxLength": 4096
            },
            "order_number": {
              "type": "string",
              "description": "order_number",
              "minLength": 1,
              "maxLength": 4096
            },
            "sender_name": {
              "type": "string",
              "description": "sender_name",
              "minLength": 1,
              "maxLength": 4096
            },
            "reason_note": {
              "type": "string",
              "description": "reason_note",
              "minLength": 1,
              "maxLength": 4096
            }
          },
          "additionalProperties": true,
          "minProperties": 1
        }
      },
      "required": [
        "body"
      ],
      "additionalProperties": false
    },
    "scope": "returns:write"
  },
  {
    "name": "announce_inbound",
    "description": "Announce a real inbound shipment. Use a stable idempotency_key to avoid duplicates.",
    "method": "POST",
    "path": "/v1/inbound",
    "inputSchema": {
      "type": "object",
      "properties": {
        "body": {
          "type": "object",
          "properties": {
            "inbound_number": {
              "type": "string",
              "description": "Inbound reference",
              "minLength": 1,
              "maxLength": 4096
            },
            "expected_date": {
              "type": "string",
              "format": "date"
            },
            "external_ref": {
              "type": "string",
              "description": "External unique reference",
              "minLength": 1,
              "maxLength": 4096
            },
            "external_source": {
              "type": "string",
              "description": "External source, for example shopify",
              "minLength": 1,
              "maxLength": 4096
            },
            "items": {
              "type": "array",
              "minItems": 1,
              "items": {
                "type": "object",
                "properties": {
                  "product_id": {
                    "type": "string",
                    "description": "Subke product ID",
                    "minLength": 1,
                    "maxLength": 4096
                  },
                  "packaging_level_id": {
                    "type": "string",
                    "description": "Subke packaging level ID",
                    "minLength": 1,
                    "maxLength": 4096
                  },
                  "expected_quantity": {
                    "type": "number",
                    "exclusiveMinimum": 0
                  },
                  "external_ref": {
                    "type": "string",
                    "description": "Optional external line reference",
                    "minLength": 1,
                    "maxLength": 4096
                  }
                },
                "required": [
                  "product_id",
                  "packaging_level_id",
                  "expected_quantity"
                ],
                "additionalProperties": true
              }
            }
          },
          "required": [
            "inbound_number",
            "items"
          ],
          "additionalProperties": true
        },
        "idempotency_key": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200,
          "description": "Stable unique identifier for this intended creation. Reuse when retrying the same operation."
        }
      },
      "required": [
        "body",
        "idempotency_key"
      ],
      "additionalProperties": false
    },
    "scope": "inbound:write"
  },
  {
    "name": "update_inbound",
    "description": "Change a live inbound: add_items, remove_items, update_quantities or cancel. Confirm the intended inbound and change from user context before calling.",
    "method": "PATCH",
    "path": "/v1/inbound/{id}",
    "inputSchema": {
      "type": "object",
      "properties": {
        "body": {
          "type": "object",
          "properties": {
            "action": {
              "type": "string",
              "enum": [
                "add_items",
                "remove_items",
                "update_quantities",
                "cancel"
              ]
            },
            "items": {
              "type": "array",
              "minItems": 1,
              "items": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": true
              }
            }
          },
          "required": [
            "action"
          ],
          "additionalProperties": true
        },
        "id": {
          "type": "string",
          "description": "Subke inbound ID",
          "minLength": 1,
          "maxLength": 4096
        }
      },
      "required": [
        "body",
        "id"
      ],
      "additionalProperties": false
    },
    "scope": "inbound:write"
  }
];
