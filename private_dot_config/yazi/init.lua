function Status:name()
	local h = self._tab.current.hovered
	if not h then
		return ui.Line({})
	end

	local linked = ""
	if h.link_to ~= nil then
		linked = " -> " .. tostring(h.link_to)
	end
	return ui.Line(" " .. h.name .. linked)
end

-- Record every directory change, including Z jumps and folders passed through,
-- so j in fish and Z here share the same directory history.
require("zoxide"):setup({ update_db = true })
