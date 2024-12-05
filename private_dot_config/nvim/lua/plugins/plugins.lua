require("gitsigns").setup({
  current_line_blame = true,
})

return {
  {
    "nvim-zh/colorful-winsep.nvim",
    config = true,
    event = { "WinLeave" },
  },
  {
    "smjonas/inc-rename.nvim",
    event = "VeryLazy",
  },
}
