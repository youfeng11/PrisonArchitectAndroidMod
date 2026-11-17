/* Mod research compatibility for the tablet interface. */
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

static bool available(JsonValue *records, Position candidate) {
    /* Keep the bottom-right Close button clear. The rest of the normalized
     * grid follows the original tablet tree's icon and row spacing. */
    if (candidate.y < -0.85f && candidate.x > 0.75f) return false;
    unsigned count = json_size(records);
    for (unsigned i = 0; i < count; ++i) {
        Position occupied = position(json_index(records, i));
        float dx = occupied.x - candidate.x, dy = occupied.y - candidate.y;
        if (dx < 0) dx = -dx;
        if (dy < 0) dy = -dy;
        if (dx < 0.075f && dy < 0.105f) return false;
    }
    return true;
}

static Position place_research(JsonValue *records, JsonValue *parent) {
    static const float columns[] = {0.0408f, 0.1427f, 0.2590f, 0.3560f, 0.4606f, 0.5648f, 0.6975f, 0.8043f, 0.9050f};
    static const float rows[] = {-0.2658f, -0.4017f, -0.5292f, -0.6524f, -0.7841f, -0.9160f};
    Position origin = position(parent), best = {origin.x, origin.y - 0.132f};
    float score = 1000000.0f;
    for (unsigned y = 0; y < sizeof(rows) / sizeof(*rows); ++y) {
        for (unsigned x = 0; x < sizeof(columns) / sizeof(*columns); ++x) {
            Position candidate = {columns[x], rows[y]};
            if (!available(records, candidate)) continue;
            float dx = candidate.x - origin.x, dy = candidate.y - (origin.y - 0.132f);
            float distance = dx * dx + 4.0f * dy * dy;
            if (candidate.y >= origin.y) distance += 1.0f;
            if (distance < score) { best = candidate; score = distance; }
        }
    }
    return best;
}

void read_mod_research_json(int location, const GameString *path, JsonValue *root) {
    read_research_json_original(location, path, root);
    JsonValue *records = json_member(root, "ResearchData");
    if (!json_is_array(records)) return;
    unsigned original_count = json_size(records);
    if (!original_count) return;
    /* The stock loader assigns research IDs in JSON order starting at one.
     * ResearchSystem appends new definitions after these built-in IDs. */
    unsigned count = research_item_count();
    for (unsigned id = original_count + 1; id < count; ++id) {
        const ResearchItem *item = research_item(id);
        unsigned parent_id = item->required > 0 && (unsigned)item->required <= json_size(records) ? item->required : 1;
        JsonValue *parent = json_index(records, parent_id - 1);
        Position slot = place_research(records, parent);
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
}
