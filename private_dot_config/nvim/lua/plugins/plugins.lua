require("gitsigns").setup({
  current_line_blame = true,
})

return {
  {
    "folke/snacks.nvim",
    opts = {
      scroll = {
        animate = false,
        filter = function()
          return false
        end,
      },
    },
  },
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
