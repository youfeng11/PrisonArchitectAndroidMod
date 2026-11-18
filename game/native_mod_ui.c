/* Mod compatibility fixes for the tablet's research and program interfaces. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

typedef union {
    uint8_t short_size;
    struct { unsigned capacity, size; const char *data; } long_string;
} GameString;
typedef struct { uint64_t opaque[3]; } JsonValue;
typedef struct {
    GameString name;
    uint8_t reserved[12];
    int type, required, administrator, sprite, cost;
} ResearchItem;
typedef struct { float x, y; } Position;
typedef struct { unsigned original_count; float scale; } ResearchPlacementState;
typedef struct {
    Position at;
    unsigned parent, depth;
    float scale;
    bool placed;
} ResearchPlacement;

extern void read_research_json_original(int, const GameString *, JsonValue *);
extern int research_item_count(void);
extern const ResearchItem *research_item(int);
extern JsonValue *json_member(JsonValue *, const char *);
extern JsonValue *json_index(JsonValue *, unsigned);
extern unsigned json_size(const JsonValue *);
extern bool json_is_array(const JsonValue *);
extern void json_construct(JsonValue *, int);
extern void json_construct_text(JsonValue *, const char *);
extern void json_construct_int(JsonValue *, int);
extern void json_construct_real(JsonValue *, double);
extern void json_destroy(JsonValue *);
extern void json_swap(JsonValue *, JsonValue *);
extern void json_append(JsonValue *, const JsonValue *);
extern void json_text(GameString *, const JsonValue *);
extern float json_real(const JsonValue *);
extern void *new_array(unsigned);
extern void delete_array(void *);
extern void delete_object(void *);
extern void copy_bytes(void *, const void *, unsigned);
extern ResearchPlacementState *research_placement_state(void);
extern void debug_log(const char *, ...);

static const char *text(const GameString *value) {
    return value->short_size & 1 ? value->long_string.data : (const char *)value + 1;
}

static void set_text(JsonValue *node, const char *key, const char *value) {
    JsonValue temporary;
    json_construct_text(&temporary, value);
    json_swap(json_member(node, key), &temporary);
    json_destroy(&temporary);
}

static void set_int(JsonValue *node, const char *key, int value) {
    JsonValue temporary;
    json_construct_int(&temporary, value);
    json_swap(json_member(node, key), &temporary);
    json_destroy(&temporary);
}

static void set_real(JsonValue *node, const char *key, double value) {
    JsonValue temporary;
    json_construct_real(&temporary, value);
    json_swap(json_member(node, key), &temporary);
    json_destroy(&temporary);
}

static void set_label(JsonValue *node, const char *key, const char *prefix, const char *name) {
    unsigned a = strlen(prefix), b = strlen(name);
    char *label = new_array(a + b + 1);
    copy_bytes(label, prefix, a);
    copy_bytes(label + a, name, b + 1);
    set_text(node, key, label);
    delete_array(label);
}

static Position position(JsonValue *node) {
    return (Position){json_real(json_member(node, "xpos")), json_real(json_member(node, "ypos"))};
}

static bool available(const ResearchPlacement *nodes, unsigned count, Position candidate, float scale) {
    if (candidate.x < 0.025f || candidate.x > 0.965f - 0.055f * scale ||
            candidate.y > -0.255f - 0.01f * scale || candidate.y < -0.985f + 0.07f * scale) return false;
    /* Reserve the close button, including the new node's padded footprint. */
    if (candidate.x + 0.0375f * scale > 0.79f && candidate.y - 0.0525f * scale < -0.90f) return false;
    for (unsigned i = 1; i < count; ++i) {
        if (!nodes[i].placed) continue;
        float dx = nodes[i].at.x - candidate.x, dy = nodes[i].at.y - candidate.y;
        if (dx < 0) dx = -dx;
        if (dy < 0) dy = -dy;
        float sizes = nodes[i].scale + scale;
        if (dx < 0.0375f * sizes + 0.001f && dy < 0.0525f * sizes + 0.001f) return false;
    }
    return true;
}

static void consider_slot(const ResearchPlacement *nodes, unsigned count, Position origin,
        float target_y, float scale, Position candidate, Position *best, float *score) {
    if (!available(nodes, count, candidate, scale)) return;
    float dx = candidate.x - origin.x, dy = candidate.y - target_y;
    float distance = dx * dx + 2.0f * dy * dy;
    if (candidate.y >= origin.y) distance += 0.5f;
    if (distance < *score) { *best = candidate; *score = distance; }
}

static bool place_research(const ResearchPlacement *nodes, unsigned count, unsigned original_count,
        unsigned parent, float scale, Position *result) {
    Position origin = nodes[parent].at;
    float target_y = origin.y - 0.066f * (nodes[parent].scale + scale);
    float score = 1000000.0f;
    consider_slot(nodes, count, origin, target_y, scale, (Position){origin.x, target_y}, result, &score);
    if (score == 0) return true;
    float x_step = 0.075f * scale + 0.004f, y_step = 0.105f * scale + 0.004f;
    unsigned columns = (unsigned)(0.94f / x_step) + 1, rows = (unsigned)(0.74f / y_step) + 1;
    /* Sample both grid phases and the existing branch columns. This also uses
     * gaps between the old nine columns instead of restricting all additions
     * to the same small list of coordinates. All collision checks use RAM. */
    for (unsigned phase_y = 0; phase_y < 2; ++phase_y) for (unsigned row = 0; row <= rows + 2; ++row) {
        if (phase_y && row > rows) continue;
        float y = -0.2658f - (row + phase_y * 0.5f) * y_step;
        if (row == rows + 1) y = -0.985f + 0.07f * scale;
        if (row == rows + 2) y = target_y;
        consider_slot(nodes, count, origin, target_y, scale, (Position){origin.x, y}, result, &score);
        for (unsigned id = 1; id <= original_count; ++id)
            consider_slot(nodes, count, origin, target_y, scale, (Position){nodes[id].at.x, y}, result, &score);
        for (unsigned phase_x = 0; phase_x < 2; ++phase_x) for (unsigned col = 0; col <= columns; ++col) {
            float x = 0.025f + (col + phase_x * 0.5f) * x_step;
            consider_slot(nodes, count, origin, target_y, scale, (Position){x, y}, result, &score);
        }
    }
    return score < 1000000.0f;
}

static unsigned original_ancestor(const ResearchPlacement *nodes, unsigned count, unsigned original_count, unsigned id) {
    for (unsigned steps = 0; id > original_count && id < count && steps < count; ++steps) id = nodes[id].parent;
    return id && id <= original_count ? id : 1;
}

static float arrange_research(ResearchPlacement *nodes, unsigned count, unsigned original_count) {
    unsigned unresolved = count - original_count - 1, deepest = 0;
    while (unresolved) {
        unsigned progress = 0;
        for (unsigned id = original_count + 1; id < count; ++id) {
            if (nodes[id].depth != ~0u) continue;
            unsigned parent = nodes[id].parent;
            if (parent > original_count && nodes[parent].depth == ~0u) continue;
            nodes[id].depth = parent > original_count ? nodes[parent].depth + 1 : 0;
            if (nodes[id].depth > deepest) deepest = nodes[id].depth;
            --unresolved;
            ++progress;
        }
        if (!progress) for (unsigned id = original_count + 1; id < count; ++id) {
            if (nodes[id].depth != ~0u) continue;
            /* Break only placement traversal for cyclic prerequisites. The
             * actual ResearchSystem prerequisite and ID remain untouched. */
            nodes[id].depth = 0;
            --unresolved;
            break;
        }
    }
    float scale = 1.0f;
    for (;;) {
        for (unsigned id = original_count + 1; id < count; ++id) {
            nodes[id].placed = false;
            nodes[id].scale = scale;
        }
        bool fits = true;
        for (unsigned depth = 0; depth <= deepest && fits; ++depth) {
            for (unsigned id = original_count + 1; id < count; ++id) {
                if (nodes[id].depth != depth) continue;
                unsigned parent = nodes[id].parent;
                if (!parent || !nodes[parent].placed) parent = original_ancestor(nodes, count, original_count, id);
                if (!place_research(nodes, count, original_count, parent, scale, &nodes[id].at)) {
                    fits = false;
                    break;
                }
                nodes[id].placed = true;
            }
        }
        if (fits) return scale;
        scale *= 0.9f;
    }
}

void read_mod_research_json(int location, const GameString *path, JsonValue *root) {
    read_research_json_original(location, path, root);
    JsonValue *records = json_member(root, "ResearchData");
    if (!json_is_array(records)) return;
    unsigned original_count = json_size(records);
    ResearchPlacementState *state = research_placement_state();
    *state = (ResearchPlacementState){original_count, 1.0f};
    if (!original_count) return;
    /* The stock loader assigns research IDs in JSON order starting at one.
     * ResearchSystem appends new definitions after these built-in IDs. */
    unsigned count = research_item_count();
    if (count <= original_count + 1) return;
    ResearchPlacement *nodes = new_array(sizeof(*nodes) * count);
    for (unsigned id = 1; id < count; ++id) {
        int parent = research_item(id)->required;
        nodes[id].parent = parent > 0 && (unsigned)parent < count && (unsigned)parent != id ? (unsigned)parent : 0;
        nodes[id].depth = id <= original_count ? 0 : ~0u;
        nodes[id].scale = 1.0f;
        nodes[id].placed = id <= original_count;
        if (id <= original_count) nodes[id].at = position(json_index(records, id - 1));
    }
    state->scale = arrange_research(nodes, count, original_count);
    for (unsigned id = original_count + 1; id < count; ++id) {
        const ResearchItem *item = research_item(id);
        unsigned parent_id = original_ancestor(nodes, count, original_count, id);
        JsonValue *parent = json_index(records, parent_id - 1);
        Position slot = nodes[id].at;
        GameString icon = {0};
        json_text(&icon, json_member(parent, "icon"));
        JsonValue entry;
        json_construct(&entry, 7);
        set_label(&entry, "research_name", "research_", text(&item->name));
        set_label(&entry, "research_description", "researchtooltip_", text(&item->name));
        set_text(&entry, "icon", text(&icon));
        set_int(&entry, "cost", item->cost < 0 ? -item->cost : item->cost);
        set_real(&entry, "xpos", slot.x);
        set_real(&entry, "ypos", slot.y);
        json_append(records, &entry);
        json_destroy(&entry);
        if (icon.short_size & 1) delete_object((void *)icon.long_string.data);
    }
    if (state->scale < 0.999f) debug_log("PATools research: fitted %u added nodes at %u%% of original size\n",
        count - original_count - 1, (unsigned)(state->scale * 100));
    delete_array(nodes);
}

extern void original_add_research_widget(void *, const void *);
extern unsigned research_widget_id(const void *);
extern void scale_research_widget(void *, const Position *);

void add_sized_research_widget(void *parent, const void *shared_widget, const void *element) {
    original_add_research_widget(parent, shared_widget);
    const ResearchPlacementState *state = research_placement_state();
    if (state->scale < 0.999f && research_widget_id(element) > state->original_count) {
        void *widget = *(void *const *)shared_widget;
        scale_research_widget(widget, &(Position){state->scale, state->scale});
    }
}

typedef struct { void *widget, *control; } SharedWidget;
extern void original_program_entry(SharedWidget *, void *, const void *);
extern void widget_child(SharedWidget *, void *, const GameString *);
extern void widget_consume_input(void *, bool);
extern void release_widget_reference(void *);

static void allow_parent_gestures(void *root, const char *name) {
    unsigned length = strlen(name);
    GameString key = {.long_string = {((length + 2) & ~1u) | 1u, length, name}};
    SharedWidget child = {0};
    widget_child(&child, root, &key);
    if (child.widget) widget_consume_input(child.widget, false);
    if (child.control) release_widget_reference(child.control);
}

void create_scrollable_program_entry(SharedWidget *result, void *screen, const void *title) {
    original_program_entry(result, screen, title);
    /* Keep native enabled states and click delegates. Only let gestures bubble
     * to the enclosing ScrollView, including drags beginning on disabled rows. */
    widget_consume_input(result->widget, false);
    allow_parent_gestures(result->widget, "ReportsTabContentButton");
    allow_parent_gestures(result->widget, "NewProgramsDisabledInputs");
}
