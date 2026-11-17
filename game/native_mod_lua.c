/* Lua API additions for the pinned Android v49 engine. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef struct lua_State lua_State;
typedef int (*LuaFunction)(lua_State *);
typedef struct { const char *name; LuaFunction function; } LuaRegistration;
typedef struct { int index, unique; } ObjectId;
typedef union {
    uint8_t short_size;
    struct { unsigned capacity, size; const char *data; } long_string;
} GameString;

typedef struct {
    uint8_t reserved0[12];
    int id;
    uint8_t reserved1[4];
    int kind;
    uint8_t reserved2[72];
    ObjectId target;
    uint8_t reserved3[12];
    GameString action;
} WorkItem;
typedef struct { WorkItem **items; int capacity, count; } WorkQueue;

_Static_assert(offsetof(WorkItem, target) == 0x60, "v49 custom job target");
_Static_assert(offsetof(WorkItem, action) == 0x74, "v49 custom job name");

extern void luaL_register(lua_State *, const char *, const LuaRegistration *);
extern int lua_gettop(lua_State *);
extern int lua_type(lua_State *, int);
extern void lua_getfield(lua_State *, int, const char *);
extern void lua_setfield(lua_State *, int, const char *);
extern void lua_settop(lua_State *, int);
extern const char *lua_tolstring(lua_State *, int, unsigned *);
extern int lua_tointeger(lua_State *, int);
extern void lua_pushcclosure(lua_State *, LuaFunction, int);
extern void *game_world(void);
extern void cancel_work_job(WorkQueue *, int, bool);

enum { LUA_NIL = 0, LUA_NUMBER = 3, LUA_STRING = 4, LUA_TABLE = 5, LUA_GLOBALS = -10002 };

/* Object proxies expose the same hidden ID fields read by LuaWobj::GetObjectId. */
static bool object_id(lua_State *state, int table, ObjectId *id) {
    if (lua_type(state, table) != LUA_TABLE) return false;
    int top = lua_gettop(state);
    lua_getfield(state, table, "id-index");
    lua_getfield(state, table, "id-uniqueId");
    int index_type = lua_type(state, -2), unique_type = lua_type(state, -1);
    bool valid = (index_type == LUA_STRING || index_type == LUA_NUMBER) &&
                 (unique_type == LUA_STRING || unique_type == LUA_NUMBER);
    if (valid) {
        id->index = lua_tointeger(state, -2);
        id->unique = lua_tointeger(state, -1);
        valid = id->index != -1 && id->unique != -1;
    }
    lua_settop(state, top);
    return valid;
}

static int cancel_object_job(lua_State *state) {
    int top = lua_gettop(state);
    int first = lua_type(state, 1), second = lua_type(state, 2);
    int name_index = 2, target_index = 1;
    if (first == LUA_STRING && (second == LUA_NIL || second == -1)) {
        name_index = 1;
        lua_getfield(state, LUA_GLOBALS, "me");
        target_index = lua_gettop(state);
    } else if (first == LUA_NIL || first == -1) {
        lua_getfield(state, LUA_GLOBALS, "me");
        target_index = lua_gettop(state);
    } else if (first == LUA_STRING) {
        const char *name = lua_tolstring(state, 1, NULL);
        lua_getfield(state, LUA_GLOBALS, name);
        target_index = lua_gettop(state);
    }
    ObjectId target;
    if (!object_id(state, target_index, &target) || lua_type(state, name_index) != LUA_STRING) {
        lua_settop(state, top);
        return 0;
    }
    unsigned length;
    const char *name = lua_tolstring(state, name_index, &length);
    uint8_t *world = game_world();
    if (world) {
        WorkQueue *queue = (WorkQueue *)(world + 0x5c);
        /* CancelJob removes a single entry; reverse traversal retains every
         * earlier index and does not leave duplicate matching jobs behind. */
        for (int i = queue->count - 1; i >= 0; --i) {
            const WorkItem *item = queue->items[i];
            if (item->kind != 21 || item->target.index != target.index || item->target.unique != target.unique) continue;
            const GameString *action = &item->action;
            unsigned size = action->short_size & 1 ? action->long_string.size : action->short_size >> 1;
            const char *text = action->short_size & 1 ? action->long_string.data : (const char *)action + 1;
            if (size == length && !memcmp(text, name, length)) cancel_work_job(queue, item->id, false);
        }
    }
    lua_settop(state, top);
    return 0;
}

void register_object_lua(lua_State *state, const char *name, const LuaRegistration *original) {
    luaL_register(state, name, original);
    lua_pushcclosure(state, cancel_object_job, 0);
    lua_setfield(state, -2, "CancelJob");
}
