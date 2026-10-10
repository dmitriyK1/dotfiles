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

-- Uncomment to add every folder opened in yazi to zoxide's database, like a `cd` in fish does,
-- so `j` in the shell and `Z` here can jump to folders you browsed to in yazi. Off by default
-- because folders you only pass through while browsing get counted too.
-- require("zoxide"):setup({ update_db = true })
