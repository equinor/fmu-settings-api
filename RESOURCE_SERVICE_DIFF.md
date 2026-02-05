# Summary

## Methods Added

### `ResourceService.get_cache_diff(resource, revision_id)`

Compares the current resource (config or mappings) against a cached revision.
Returns a list of diff entries.

Response shape:

For non‑list fields (scalar):

- `field_path`
- `updated: { before, after }`

For list fields in `_LIST_DIFF_KEYS`:

- `field_path`
- `added`, `removed`, `updated` (per‑item diffs)

### `ResourceService._build_list_diff(current, selected, key_field)`

Builds per‑item diffs for list fields. Items are matched by:

- a field name (like `name`, `uuid`)
- or `"__full__"` which treats the whole item as identity (used for mappings)

Returns:

- `added`: items only in the selected revision
- `removed`: items only in current
- `updated`: items in both but with different content

Think of this from a “Restore this revision” point of view:

- For scalar fields, `after` is the value that will replace `before`.
- For list fields, items in `added/removed/updated` describe exactly what will change if you restore.

## What Plain `get_model_diff` Does

`get_model_diff` treats lists as a single value. If one item changes, you get the whole list back.

Assume these changes happened if you restore to the selected revision:

- `model.revision`: `øo -> ooo`
- `rms.horizons`: `MSL` type changes, and `BaseVolantis` is added

### A) Plain `get_model_diff` output

```json
[
  {
    "field_path": "model.revision",
    "current": "øo",
    "selected": "ooo"
  },
  {
    "field_path": "rms.horizons",
    "current": [
      { "name": "MSL", "type": "calculated" },
      { "name": "TopVolantis", "type": "interpreted" }
    ],
    "selected": [
      { "name": "MSL", "type": "interpreted" },
      { "name": "TopVolantis", "type": "interpreted" },
      { "name": "BaseVolantis", "type": "interpreted" }
    ]
  }
]
```

This is noisy because the whole list shows up.

### B) Current API output

```json
[
  {
    "field_path": "model.revision",
    "updated": { "before": "øo", "after": "ooo" }
  },
  {
    "field_path": "rms.horizons",
    "added": [{ "name": "BaseVolantis", "type": "interpreted" }],
    "removed": [],
    "updated": [
      {
        "key": "MSL",
        "before": { "name": "MSL", "type": "calculated" },
        "after": { "name": "MSL", "type": "interpreted" }
      }
    ]
  }
]
```

Example for strat mappings, no difference with `get_model_diff`

```json
[
  {
    "field_path": "stratigraphy.root",
    "added": [
      {
        "source_system": "rms",
        "target_system": "smda",
        "mapping_type": "stratigraphy",
        "relation_type": "primary",
        "source_id": "Viking Group",
        "source_uuid": "3fa85f64-5717-4562-b3fc-2c963f66af43",
        "target_id": "VIKING GP.",
        "target_uuid": "3fa85f64-5717-4562-b3fc-2c963f66afb6"
      }
    ],
    "removed": [
      {
        "source_system": "rms",
        "target_system": "smda",
        "mapping_type": "stratigraphy",
        "relation_type": "alias",
        "source_id": "Viking Group",
        "source_uuid": "3fa85f64-5717-4562-b3fc-2c963f66af43",
        "target_id": "VIKING GP.",
        "target_uuid": "3fa85f64-5717-4562-b3fc-2c963f66afb6"
      }
    ],
    "updated": []
  }
]
```

Because identity is the full item, changes show up as remove + add, not update.

## Moving Diff Logic Out Of The API

If we move list diffing into `fmu-settings`, there are two reasonable ways to do it.

### Option A: Put identity in the models (requires datamodel changes)

Add a stable identity field (or a modeled composite) to list item models so diffing can match items without a config map.

What changes:

- `fmu-datamodels`: add identity fields to list item models like `masterdata.smda.country`
- `fmu-settings`: add identity fields to list item models like `rms.zones`, update `get_model_diff` to use those identity fields for list diffs

Tradeoff:

- More invasive, but no `_LIST_DIFF_KEYS` map to maintain

### Option B: Keep an identity map in `fmu-settings` (no datamodel changes)

Move `_LIST_DIFF_KEYS` into `fmu-settings` and use it inside `get_model_diff`.

What changes:

- `fmu-settings`: add a list identity map (e.g., `rms.zones -> name`, `masterdata.smda.field -> uuid`, `stratigraphy.root -> __full__`) and update `get_model_diff` to call list diff logic when a path matches
- `fmu-datamodels`: no change

Tradeoff:

- Easy but you have to keep the map in sync with schema changes
