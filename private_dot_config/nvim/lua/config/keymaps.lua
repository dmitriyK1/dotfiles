-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

vim.keymap.set("i", "jj", "<ESC>l", { silent = true })

function InsertDate()
  local date_string = os.date("================ %Y-%m-%d %H:%M:%S | ================")
  vim.api.nvim_put({ date_string }, "c", true, true)
end

vim.keymap.set("n", "<leader>id", InsertDate, { desc = "Insert Date" })
