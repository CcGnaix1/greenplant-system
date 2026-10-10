// pages/export/export.js
const api = require('../../utils/request')
const app = getApp()

Page({
  data: { fmt: 'pdf' },
  pick(e) { this.setData({ fmt: e.currentTarget.dataset.f }) },
  doExport() {
    wx.showLoading({ title: '正在生成' })
    api.call('/export/records', { data: { format: this.data.fmt } }).then(res => {
      const fileUrl = res.data && res.data.fileUrl
      if (!fileUrl) throw new Error('后端未返回文件地址')
      const origin = app.globalData.baseUrl.replace(/\/api\/?$/, '')
      wx.downloadFile({
        url: origin + fileUrl,
        header: { Authorization: 'Bearer ' + app.globalData.token },
        success: result => {
          wx.hideLoading()
          if (result.statusCode !== 200) {
            wx.showToast({ title: '文件下载失败', icon: 'none' })
            return
          }
          wx.openDocument({
            filePath: result.tempFilePath,
            fileType: this.data.fmt === 'excel' ? 'xlsx' : 'pdf',
            showMenu: true,
            fail: () => wx.showToast({ title: '无法打开文件', icon: 'none' })
          })
        },
        fail: () => {
          wx.hideLoading()
          wx.showToast({ title: '文件下载失败', icon: 'none' })
        }
      })
    }).catch(err => {
      wx.hideLoading()
      wx.showToast({ title: err.message || '导出失败', icon: 'none' })
    })
  }
})
