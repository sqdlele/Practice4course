var Cart = (function() {
    var STORAGE_KEY = 'chistotut_cart';

    function load() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
        } catch(e) { return []; }
    }

    function save(items) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
        updateBadge();
    }

    function getAll() { return load(); }

    function get(serviceId) {
        return load().find(function(i) { return i.service_id === serviceId; }) || null;
    }

    function set(item) {
        var items = load();
        var idx = items.findIndex(function(i) { return i.service_id === item.service_id; });
        if (idx >= 0) items[idx] = item;
        else items.push(item);
        save(items);
    }

    function remove(serviceId) {
        var items = load().filter(function(i) { return i.service_id !== serviceId; });
        save(items);
    }

    function clear() { save([]); }

    function totalCount() {
        return load().reduce(function(s, i) { return s + (i.qty || 0); }, 0);
    }

    function updateBadge() {
        var badges = document.querySelectorAll('.cart-badge');
        var count = totalCount();
        badges.forEach(function(b) {
            b.textContent = count;
            b.style.display = count > 0 ? 'flex' : 'none';
        });
    }

    document.addEventListener('DOMContentLoaded', updateBadge);

    return {
        getAll: getAll,
        get: get,
        set: set,
        remove: remove,
        clear: clear,
        totalCount: totalCount,
        updateBadge: updateBadge,
    };
})();
