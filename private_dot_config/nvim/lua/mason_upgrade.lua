-- Upgrades every installed Mason package; run headless by ~/.local/bin/update.fish.
-- Mason has no command for this (:MasonUpdate only refreshes registries), so this
-- does what the Mason UI's "update all" does: install the latest version over outdated packages.

local function say(...)
  -- headless print() can run lines together
  io.write(table.concat({ ... }), "\n")
end

local has_mason, registry = pcall(require, "mason-registry")
if not has_mason then
  say("mason is not installed, skipping")
  return
end

-- Calls a callback-style Mason API and waits for its (success, result) callback.
local function await(start)
  local result
  start(function(...)
    result = { ... }
  end)
  if not vim.wait(600000, function()
    return result ~= nil
  end, 100) then
    return false, "timed out"
  end
  return unpack(result)
end

local failed = false
local updated, update_err = await(registry.update)
if not updated then
  say("registry update failed: ", vim.inspect(update_err))
  failed = true
else
  local upgraded = 0
  for _, pkg in ipairs(registry.get_installed_packages()) do
    local ok, err = pcall(function()
      local current, latest = pkg:get_installed_version(), pkg:get_latest_version()
      if current == latest then
        return
      end
      say(pkg.name, ": ", tostring(current), " -> ", latest)
      local installed, install_err = await(function(cb)
        pkg:install({}, cb)
      end)
      if not installed then
        error(install_err, 0)
      end
      upgraded = upgraded + 1
    end)
    if not ok then
      say(pkg.name, ": upgrade failed: ", vim.inspect(err))
      failed = true
    end
  end
  if upgraded == 0 and not failed then
    say("all Mason packages are up to date")
  end
end

-- Lua errors and plain returns in headless +lua still exit 0, which would hide failures.
if failed then
  vim.cmd.cquit(1)
end
